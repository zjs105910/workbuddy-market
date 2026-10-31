import { firstValue, hasSwitch, parseArguments, readBody } from "./arguments";
import { latestRuns, rollupConclusion } from "./checks";
import { type CommandContext, type CommandOutcome, fail, succeed } from "./context";
import { currentBranch, remoteHead, runGit } from "./git";
import { findPullRequest, pullRequestUrl, refresh, releaseThreads } from "./pullRequests";

const valueFlags = [
  "--title", "-t", "--body", "-b", "--body-file", "-F", "--base", "-B", "--head", "-H",
  "--assignee", "-a", "--label", "-l", "--reviewer", "-r", "--milestone", "-m", "--project", "-p",
  "--add-label", "--remove-label", "--add-reviewer", "--remove-reviewer", "--add-assignee", "--repo", "-R",
  "--subject", "--match-head-commit",
];

function fillBody(options: { readonly context: CommandContext; readonly base: string; readonly head: string }): string {
  return runGit({
    cwd: options.context.workspace.remoteDirectory,
    args: ["log", "--format=%s%n%n%b", `${options.base}..${options.head}`],
  }).stdout.trim();
}

export function createPullRequest(context: CommandContext): CommandOutcome {
  const parsed = parseArguments({ args: context.args, valueFlags });
  const head = firstValue({ parsed, names: ["--head", "-H"] }) ?? currentBranch(context.cwd) ?? "";
  const base = firstValue({ parsed, names: ["--base", "-B"] }) ?? context.state.defaultBranch;

  if (remoteHead({ remoteDirectory: context.workspace.remoteDirectory, branch: head }) === null) {
    return fail({ operation: "pr-create", message: `aborted: you must first push the current branch to a remote, or use the --head flag` });
  }

  const existing = context.state.pullRequests.find((pullRequest) => pullRequest.head === head && pullRequest.state === "OPEN");

  if (existing) {
    return fail({
      operation: "pr-create",
      message: `a pull request for branch "${head}" into branch "${existing.base}" already exists:\n${pullRequestUrl({ state: context.state, number: existing.number })}`,
    });
  }

  const fill = hasSwitch({ parsed, names: ["--fill", "-f", "--fill-first", "--fill-verbose"] });
  const number = context.state.nextPullRequest;
  const title = firstValue({ parsed, names: ["--title", "-t"] }) ?? (fill ? head : "");
  const body = readBody({ parsed, cwd: context.cwd }) ?? (fill ? fillBody({ context, base, head }) : "");

  if (title.length === 0) {
    return fail({ operation: "pr-create", message: "must provide `--title` and `--body` (or `--fill`) when not running interactively" });
  }

  context.state.nextPullRequest += 1;
  context.state.pullRequests.push({
    number,
    title,
    body,
    head,
    base,
    draft: hasSwitch({ parsed, names: ["--draft", "-d"] }),
    approved: false,
    state: "OPEN",
    initialHead: null,
  });
  releaseThreads({ state: context.state, pullRequest: number, trigger: "pr-created" });
  refresh({ workspace: context.workspace, state: context.state });

  return succeed({
    operation: "pr-create",
    stdout: `${pullRequestUrl({ state: context.state, number })}\n`,
    details: { number, title, body, head, base, draft: hasSwitch({ parsed, names: ["--draft", "-d"] }) },
  });
}

export function markReady(context: CommandContext): CommandOutcome {
  const parsed = parseArguments({ args: context.args, valueFlags });
  const pullRequest = findPullRequest({ state: context.state, selector: parsed.positionals[0], cwd: context.cwd });

  if (!pullRequest) {
    return fail({ operation: "pr-ready", message: "no pull requests found for branch" });
  }

  const undo = hasSwitch({ parsed, names: ["--undo"] });
  const head = remoteHead({ remoteDirectory: context.workspace.remoteDirectory, branch: pullRequest.head }) ?? "";

  pullRequest.draft = undo;

  if (!undo) {
    releaseThreads({ state: context.state, pullRequest: pullRequest.number, trigger: "ready" });
  }

  return succeed({
    operation: undo ? "pr-draft" : "pr-ready",
    stdout: `✓ Pull request #${pullRequest.number} is ${undo ? "converted to draft" : "marked as \"ready for review\""}\n`,
    details: { pullRequest: pullRequest.number, head, checks: rollupConclusion(latestRuns({ state: context.state, sha: head })) },
  });
}

export function editPullRequest(context: CommandContext): CommandOutcome {
  const parsed = parseArguments({ args: context.args, valueFlags });
  const pullRequest = findPullRequest({ state: context.state, selector: parsed.positionals[0], cwd: context.cwd });

  if (!pullRequest) {
    return fail({ operation: "pr-edit", message: "no pull requests found for branch" });
  }

  pullRequest.title = firstValue({ parsed, names: ["--title", "-t"] }) ?? pullRequest.title;
  pullRequest.body = readBody({ parsed, cwd: context.cwd }) ?? pullRequest.body;
  pullRequest.base = firstValue({ parsed, names: ["--base", "-B"] }) ?? pullRequest.base;

  return succeed({
    operation: "pr-edit",
    stdout: `${pullRequestUrl({ state: context.state, number: pullRequest.number })}\n`,
    details: { pullRequest: pullRequest.number, title: pullRequest.title, body: pullRequest.body },
  });
}

export function commentOnPullRequest(context: CommandContext): CommandOutcome {
  const parsed = parseArguments({ args: context.args, valueFlags });
  const pullRequest = findPullRequest({ state: context.state, selector: parsed.positionals[0], cwd: context.cwd });
  const body = readBody({ parsed, cwd: context.cwd });

  if (!pullRequest || body === undefined) {
    return fail({ operation: "pr-comment", message: "a pull request and --body are required when not running interactively" });
  }

  context.state.topLevelComments.push({ pullRequest: pullRequest.number, author: context.state.viewer, body });

  return succeed({
    operation: "pr-comment",
    stdout: `${pullRequestUrl({ state: context.state, number: pullRequest.number })}#issuecomment-${context.state.nextId}\n`,
    details: { pullRequest: pullRequest.number, body },
  });
}

export function changePullRequestState(options: {
  readonly context: CommandContext;
  readonly target: "MERGED" | "CLOSED";
}): CommandOutcome {
  const operation = options.target === "MERGED" ? "pr-merge" : "pr-close";
  const parsed = parseArguments({ args: options.context.args, valueFlags });
  const pullRequest = findPullRequest({ state: options.context.state, selector: parsed.positionals[0], cwd: options.context.cwd });

  if (!pullRequest) {
    return fail({ operation, message: "no pull requests found for branch" });
  }

  pullRequest.state = options.target;

  return succeed({
    operation,
    stdout: `✓ ${options.target === "MERGED" ? "Merged" : "Closed"} pull request #${pullRequest.number}\n`,
    details: { pullRequest: pullRequest.number },
  });
}

export function reviewPullRequest(context: CommandContext): CommandOutcome {
  const parsed = parseArguments({ args: context.args, valueFlags });
  const pullRequest = findPullRequest({ state: context.state, selector: parsed.positionals[0], cwd: context.cwd });
  const body = readBody({ parsed, cwd: context.cwd });

  if (pullRequest && body !== undefined && body.length > 0) {
    context.state.topLevelComments.push({ pullRequest: pullRequest.number, author: context.state.viewer, body });
  }

  return succeed({ operation: "pr-review", stdout: "", details: { pullRequest: pullRequest?.number ?? null, body: body ?? null } });
}

export function checkoutPullRequest(context: CommandContext): CommandOutcome {
  const parsed = parseArguments({ args: context.args, valueFlags });
  const pullRequest = findPullRequest({ state: context.state, selector: parsed.positionals[0], cwd: context.cwd });

  if (!pullRequest) {
    return fail({ operation: "pr-checkout", message: "no pull requests found" });
  }

  runGit({ cwd: context.cwd, args: ["fetch", "--quiet", "origin"] });

  const local = runGit({ cwd: context.cwd, args: ["rev-parse", "--verify", "--quiet", `refs/heads/${pullRequest.head}`] }).exitCode === 0;
  const result = runGit({
    cwd: context.cwd,
    args: local ? ["checkout", pullRequest.head] : ["checkout", "-b", pullRequest.head, "--track", `origin/${pullRequest.head}`],
  });

  return result.exitCode === 0
    ? succeed({ operation: "pr-checkout", stdout: result.stdout, details: { pullRequest: pullRequest.number } })
    : fail({ operation: "pr-checkout", message: result.stderr.trim() });
}
