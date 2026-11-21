import { applyJq } from "./arguments";
import { type ApiRequest, parseApiRequest, stringField } from "./apiFields";
import { latestRuns, rerunJobs } from "./checks";
import { type CommandContext, type CommandOutcome, fail, succeed, unsupported } from "./context";
import { remoteHead } from "./git";
import { graphqlMutation, graphqlQuery } from "./graphql";
import { pullRequestRecord } from "./pullRequests";
import { addReply, restComments, threadByCommentId } from "./reviews";

function respond(options: {
  readonly context: CommandContext;
  readonly request: ApiRequest;
  readonly operation: string;
  readonly value: unknown;
  readonly details?: Readonly<Record<string, unknown>>;
}): CommandOutcome {
  const rendered = applyJq({ value: options.value, expression: options.request.jq, cwd: options.context.cwd });

  return rendered.exitCode === 0
    ? succeed({ operation: options.operation, stdout: rendered.text, details: options.details })
    : fail({ operation: options.operation, message: rendered.text.trim() });
}

function pullRequestRest(options: { readonly context: CommandContext; readonly number: number }) {
  const pullRequest = options.context.state.pullRequests.find((candidate) => candidate.number === options.number);

  if (!pullRequest) {
    return undefined;
  }

  const record = pullRequestRecord({ workspace: options.context.workspace, state: options.context.state, pullRequest });

  return {
    number: pullRequest.number,
    title: pullRequest.title,
    body: pullRequest.body,
    state: pullRequest.state === "OPEN" ? "open" : "closed",
    merged: pullRequest.state === "MERGED",
    draft: pullRequest.draft,
    html_url: record.url,
    user: { login: options.context.state.viewer, type: "User" },
    head: { ref: pullRequest.head, sha: record.headRefOid },
    base: { ref: pullRequest.base, sha: remoteHead({ remoteDirectory: options.context.workspace.remoteDirectory, branch: pullRequest.base }) },
    mergeable: record.mergeable === "MERGEABLE",
    mergeable_state: String(record.mergeStateStatus).toLowerCase(),
  };
}

function restRoute(options: { readonly context: CommandContext; readonly request: ApiRequest }): CommandOutcome {
  const { context, request } = options;
  const { owner, name } = context.state.repository;
  const relative = request.endpoint
    .replace("{owner}", owner)
    .replace("{repo}", name)
    .replace(new RegExp(`^repos/${owner}/${name}/?`), "")
    .split("?")[0] ?? "";
  const segments = relative.split("/");
  const [resource, identifier, child, grandchild, leaf] = segments;
  const number = Number(identifier);
  const body = stringField({ fields: request.fields, names: ["body"] });

  if (resource === "pulls" && identifier === undefined && request.method === "GET") {
    return respond({ context, request, operation: "api-pulls", value: context.state.pullRequests.map((pullRequest) => pullRequestRest({ context, number: pullRequest.number })) });
  }

  if (resource === "pulls" && child === undefined) {
    const record = pullRequestRest({ context, number });

    return record ? respond({ context, request, operation: "api-pull", value: record }) : fail({ operation: "api-pull", message: "gh: Not Found (HTTP 404)" });
  }

  if (resource === "pulls" && child === "comments" && grandchild === undefined && request.method === "GET") {
    return respond({ context, request, operation: "api-review-comments", value: restComments({ state: context.state, pullRequest: number }) });
  }

  const replyTarget =
    resource === "pulls" && child === "comments" && leaf === "replies"
      ? Number(grandchild)
      : resource === "pulls" && child === "comments" && request.method === "POST"
        ? Number(stringField({ fields: request.fields, names: ["in_reply_to", "in_reply_to_id"] }))
        : Number.NaN;

  if (resource === "pulls" && child === "comments" && request.method === "POST") {
    const thread = threadByCommentId({ state: context.state, commentId: replyTarget });

    if (!thread || body === undefined) {
      return fail({ operation: "api-new-review-comment", message: "gh: Validation Failed (HTTP 422)", details: { pullRequest: number, body: body ?? null } });
    }

    const id = addReply({ state: context.state, thread, body });

    return respond({ context, request, operation: "reply", value: { id, body, in_reply_to_id: replyTarget }, details: { threadId: thread.id, body } });
  }

  if (resource === "pulls" && (child === "reviews" || child === "files")) {
    return respond({ context, request, operation: `api-${child}`, value: [] });
  }

  if (resource === "issues" && child === "comments") {
    if (request.method === "POST" && body !== undefined) {
      context.state.topLevelComments.push({ pullRequest: number, author: context.state.viewer, body });

      return respond({ context, request, operation: "pr-comment", value: { id: context.state.nextId, body }, details: { pullRequest: number, body } });
    }

    return respond({
      context,
      request,
      operation: "api-issue-comments",
      value: context.state.topLevelComments
        .filter((comment) => comment.pullRequest === number)
        .map((comment) => ({ body: comment.body, user: { login: comment.author, type: "User" } })),
    });
  }

  if (resource === "commits" && child === "check-runs") {
    const reference = identifier ?? "";
    const sha = /^[0-9a-f]{40}$/.test(reference) ? reference : (remoteHead({ remoteDirectory: context.workspace.remoteDirectory, branch: reference }) ?? "");
    const runs = latestRuns({ state: context.state, sha });

    return respond({
      context,
      request,
      operation: "api-check-runs",
      value: { total_count: runs.length, check_runs: runs.map((run) => ({ id: run.id, name: run.job, status: "completed", conclusion: run.conclusion, head_sha: run.sha })) },
    });
  }

  if (resource === "actions" && identifier === "runs" && (grandchild === "rerun-failed-jobs" || grandchild === "rerun")) {
    const reruns = rerunJobs({ workspace: context.workspace, state: context.state, runId: Number(child), failedOnly: grandchild === "rerun-failed-jobs" });

    return respond({ context, request, operation: "run-rerun", value: {}, details: { reruns: reruns.map((run) => run.id) } });
  }

  return unsupported(["api", request.method, request.endpoint]);
}

export function apiCommand(context: CommandContext): CommandOutcome {
  const request = parseApiRequest({ args: context.args, cwd: context.cwd });

  if (request.endpoint !== "graphql") {
    return restRoute({ context, request });
  }

  const query = stringField({ fields: request.fields, names: ["query"] }) ?? "";
  const result = /\bmutation\b/.test(query)
    ? graphqlMutation({ context, query, fields: request.fields })
    : graphqlQuery({ context, query, fields: request.fields });

  if (result === undefined) {
    return unsupported(["api", "graphql", query.replace(/\s+/g, " ").slice(0, 160)]);
  }

  return respond({ context, request, operation: result.operation, value: result.value, details: result.details });
}
