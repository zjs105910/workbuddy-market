import { stringField } from "./apiFields";
import type { CommandContext } from "./context";
import { pullRequestRecord } from "./pullRequests";
import { addReply, graphqlThreads, setResolved, threadByCommentId, threadById } from "./reviews";

export type GraphqlResult = {
  readonly operation: string;
  readonly value: unknown;
  readonly details: Readonly<Record<string, unknown>>;
};

function inlineString(options: { readonly query: string; readonly key: string }): string | undefined {
  return new RegExp(`${options.key}\\s*:\\s*"([^"]+)"`).exec(options.query)?.[1];
}

function pullRequestNumber(options: {
  readonly query: string;
  readonly fields: Readonly<Record<string, unknown>>;
}): number {
  const fromField = stringField({ fields: options.fields, names: ["number", "pr", "pull", "prNumber", "pullRequest", "pull_number"] });
  const inline = /pullRequest\s*\(\s*number\s*:\s*(\d+)/.exec(options.query)?.[1];

  return Number(fromField ?? inline);
}

export function graphqlQuery(options: {
  readonly context: CommandContext;
  readonly query: string;
  readonly fields: Readonly<Record<string, unknown>>;
}): GraphqlResult | undefined {
  const number = pullRequestNumber({ query: options.query, fields: options.fields });
  const pullRequest = options.context.state.pullRequests.find((candidate) => candidate.number === number);

  if (!pullRequest) {
    return undefined;
  }

  if (/reviewThreads/.test(options.query)) {
    return { operation: "api-review-threads", value: graphqlThreads({ state: options.context.state, pullRequest: number }), details: { pullRequest: number } };
  }

  const record = pullRequestRecord({ workspace: options.context.workspace, state: options.context.state, pullRequest });

  return {
    operation: "api-pull-graphql",
    value: {
      data: {
        repository: {
          pullRequest: {
            ...record,
            commits: { nodes: [{ commit: { oid: record.headRefOid, statusCheckRollup: { state: record.mergeStateStatus === "UNSTABLE" ? "FAILURE" : "SUCCESS", contexts: { nodes: record.statusCheckRollup } } } }] },
          },
        },
      },
    },
    details: { pullRequest: number },
  };
}

const mutationPattern = /(?:(\w+)\s*:\s*)?\b(addPullRequestReviewThreadReply|addPullRequestReviewComment|unresolveReviewThread|resolveReviewThread)\s*\(/g;

type MutationOperation = { readonly alias: string; readonly name: string; readonly segment: string };

function mutationOperations(query: string): readonly MutationOperation[] {
  const matches = [...query.matchAll(mutationPattern)];

  return matches.map((match, index) => ({
    alias: match[1] ?? match[2] ?? "",
    name: match[2] ?? "",
    segment: query.slice(match.index, matches[index + 1]?.index ?? query.length),
  }));
}

function applyMutation(options: {
  readonly context: CommandContext;
  readonly operation: MutationOperation;
  readonly fields: Readonly<Record<string, unknown>>;
  readonly single: boolean;
}): { readonly value: unknown; readonly detail: Readonly<Record<string, unknown>> } | undefined {
  const { context, operation, fields } = options;
  const fromFields = (names: readonly string[]) => (options.single ? stringField({ fields, names }) : undefined);
  const threadId =
    inlineString({ query: operation.segment, key: "threadId" }) ??
    inlineString({ query: operation.segment, key: "pullRequestReviewThreadId" }) ??
    fromFields(["threadId", "thread", "id", "pullRequestReviewThreadId"]);
  const body = inlineString({ query: operation.segment, key: "body" }) ?? fromFields(["body"]);

  if (operation.name === "resolveReviewThread" || operation.name === "unresolveReviewThread") {
    const resolved = operation.name === "resolveReviewThread";
    const thread = threadById({ state: context.state, threadId: threadId ?? "" });

    if (!thread) {
      return undefined;
    }

    setResolved({ state: context.state, thread, resolved });

    return { value: { thread: { id: thread.id, isResolved: resolved } }, detail: { operation: resolved ? "resolve" : "unresolve", threadId: thread.id } };
  }

  if (body === undefined) {
    return undefined;
  }

  const inReplyTo = inlineString({ query: operation.segment, key: "inReplyTo" }) ?? fromFields(["inReplyTo", "commentId"]);
  const thread =
    threadById({ state: context.state, threadId: threadId ?? "" }) ??
    threadByCommentId({ state: context.state, commentId: Number((inReplyTo ?? "").replace(/^PRRC_/, "")) });

  if (!thread) {
    return undefined;
  }

  const id = addReply({ state: context.state, thread, body });

  return { value: { comment: { id: `PRRC_${id}`, body } }, detail: { operation: "reply", threadId: thread.id, body } };
}

export function graphqlMutation(options: {
  readonly context: CommandContext;
  readonly query: string;
  readonly fields: Readonly<Record<string, unknown>>;
}): GraphqlResult | undefined {
  const operations = mutationOperations(options.query);
  const applied = operations.map((operation) => ({
    operation,
    result: applyMutation({ context: options.context, operation, fields: options.fields, single: operations.length === 1 }),
  }));

  if (applied.length === 0 || applied.some((entry) => entry.result === undefined)) {
    return applied.length === 0
      ? undefined
      : { operation: "mutation-failed", value: { errors: [{ message: "Could not resolve to a node with the given id" }] }, details: { failed: applied.filter((entry) => entry.result === undefined).map((entry) => entry.operation.alias) } };
  }

  const details = applied.map((entry) => entry.result?.detail ?? {});
  const operationNames = [...new Set(details.map((detail) => String(detail.operation)))];

  return {
    operation: operationNames.length === 1 ? (operationNames[0] ?? "mutation") : "mutation-batch",
    value: { data: Object.fromEntries(applied.map((entry) => [entry.operation.alias, entry.result?.value ?? null])) },
    details: { operations: details },
  };
}
