import path from "node:path";
import { applyJq, firstValue, parseArguments, pickFields } from "./arguments";
import { apiCommand } from "./api";
import { type CommandContext, type CommandOutcome, succeed, unsupported } from "./context";
import { checkoutPullRequest, commentOnPullRequest, changePullRequestState, createPullRequest, editPullRequest, markReady, reviewPullRequest } from "./prWrite";
import { listPullRequests, pullRequestChecks, pullRequestDiff, pullRequestStatus, viewPullRequest } from "./prRead";
import { logCommandFailures } from "./git";
import { refresh } from "./pullRequests";
import { listRuns, rerunRun, viewRun, watchRun } from "./runs";
import { stackCommand } from "./stack";
import { appendLog, readState, workspaceFor, writeState } from "./state";

type Handler = (context: CommandContext) => CommandOutcome;

const pullRequestHandlers: Readonly<Record<string, Handler>> = {
  create: createPullRequest,
  checkout: checkoutPullRequest,
  view: viewPullRequest,
  list: listPullRequests,
  status: pullRequestStatus,
  checks: pullRequestChecks,
  ready: markReady,
  edit: editPullRequest,
  diff: pullRequestDiff,
  comment: commentOnPullRequest,
  review: reviewPullRequest,
  merge: (context) => changePullRequestState({ context, target: "MERGED" }),
  close: (context) => changePullRequestState({ context, target: "CLOSED" }),
};

const runHandlers: Readonly<Record<string, Handler>> = {
  list: listRuns,
  view: viewRun,
  rerun: rerunRun,
  watch: watchRun,
};

function repositoryView(context: CommandContext): CommandOutcome {
  const parsed = parseArguments({ args: context.args, valueFlags: ["--json", "--jq", "-q"] });
  const { owner, name } = context.state.repository;
  const record = {
    name,
    owner: { login: owner },
    nameWithOwner: `${owner}/${name}`,
    defaultBranchRef: { name: context.state.defaultBranch },
    url: `https://github.com/${owner}/${name}`,
  };
  const json = firstValue({ parsed, names: ["--json"] });

  if (json === undefined) {
    return succeed({ operation: "repo-view", stdout: `${owner}/${name}\n` });
  }

  const rendered = applyJq({ value: pickFields({ record, fields: json }), expression: firstValue({ parsed, names: ["--jq", "-q"] }), cwd: context.cwd });

  return succeed({ operation: "repo-view", stdout: rendered.text });
}

function dispatch(context: CommandContext): CommandOutcome {
  const [group, command, ...rest] = context.args;
  const nested = { ...context, args: rest };

  if (group === undefined || group === "--version" || group === "version") {
    return succeed({ operation: "version", stdout: "gh version 2.81.0 (local stand-in)\n" });
  }

  if (group === "auth") {
    return succeed({ operation: "auth-status", stdout: `github.com\n  ✓ Logged in to github.com account ${context.state.viewer}\n` });
  }

  if (group === "repo" && command === "view") {
    return repositoryView(nested);
  }

  if (group === "pr" && command !== undefined && pullRequestHandlers[command]) {
    return pullRequestHandlers[command](nested);
  }

  if (group === "run" && command !== undefined && runHandlers[command]) {
    return runHandlers[command](nested);
  }

  if (group === "api") {
    return apiCommand({ ...context, args: context.args.slice(1) });
  }

  if (group === "stack") {
    return stackCommand({ ...context, args: context.args.slice(1) });
  }

  return unsupported(context.args);
}

export function runFakeGh(options: {
  readonly root: string;
  readonly cwd: string;
  readonly args: readonly string[];
}): CommandOutcome {
  const workspace = workspaceFor(options.root);

  logCommandFailures(path.join(workspace.stateDirectory, "command-failures.jsonl"));

  const state = readState(workspace);
  const context: CommandContext = { workspace, state, cwd: options.cwd, args: options.args };

  refresh({ workspace, state });

  const outcome = dispatch(context);

  writeState({ workspace, state });
  appendLog({
    workspace,
    entry: {
      argv: options.args,
      operation: outcome.operation,
      supported: outcome.supported,
      exitCode: outcome.exitCode,
      details: outcome.details,
    },
  });

  return outcome;
}
