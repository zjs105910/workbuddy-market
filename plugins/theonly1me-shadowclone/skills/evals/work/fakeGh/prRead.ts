import { applyJq, firstValue, hasSwitch, parseArguments, pickFields } from "./arguments";
import { type CommandContext, type CommandOutcome, fail, succeed } from "./context";
import { remoteHead, runGit } from "./git";
import { checkRollup, findPullRequest, pullRequestRecord } from "./pullRequests";

const valueFlags = ["--json", "--jq", "-q", "--state", "-s", "--head", "-H", "--base", "-B", "--limit", "-L", "--repo", "-R", "--template", "-t"];

function render(options: {
  readonly context: CommandContext;
  readonly operation: string;
  readonly value: unknown;
  readonly text: string;
  readonly parsedJson: string | undefined;
  readonly jq: string | undefined;
}): CommandOutcome {
  if (options.parsedJson === undefined) {
    return succeed({ operation: options.operation, stdout: options.text });
  }

  const rendered = applyJq({ value: options.value, expression: options.jq, cwd: options.context.cwd });

  return rendered.exitCode === 0
    ? succeed({ operation: options.operation, stdout: rendered.text })
    : fail({ operation: options.operation, message: rendered.text.trim() });
}

export function viewPullRequest(context: CommandContext): CommandOutcome {
  const parsed = parseArguments({ args: context.args, valueFlags });
  const pullRequest = findPullRequest({ state: context.state, selector: parsed.positionals[0], cwd: context.cwd });

  if (!pullRequest) {
    return fail({ operation: "pr-view", message: "no pull requests found for branch" });
  }

  const record = pullRequestRecord({ workspace: context.workspace, state: context.state, pullRequest });
  const json = firstValue({ parsed, names: ["--json"] });
  const withComments = hasSwitch({ parsed, names: ["--comments", "-c"] });
  const threads = context.state.threads.filter((thread) => thread.pullRequest === pullRequest.number && thread.released);
  const commentText = withComments
    ? threads
        .flatMap((thread) => thread.comments.map((comment) => `${comment.author} commented on ${thread.path}:${thread.line}\n${comment.body}\n`))
        .join("\n")
    : "";
  const text = [
    `${pullRequest.title} #${pullRequest.number}`,
    `${pullRequest.draft ? "Draft" : pullRequest.state === "OPEN" ? "Open" : pullRequest.state} • ${context.state.viewer} wants to merge into ${pullRequest.base} from ${pullRequest.head}`,
    `Checks: ${checkRollup({ workspace: context.workspace, state: context.state, pullRequest }).map((check) => `${String(check.name)} ${String(check.bucket)}`).join(", ") || "none"}`,
    `Mergeable: ${String(record.mergeable)}`,
    "",
    pullRequest.body,
    "",
    commentText,
    `View this pull request on GitHub: ${String(record.url)}`,
    "",
  ].join("\n");

  return render({
    context,
    operation: "pr-view",
    value: pickFields({ record, fields: json }),
    text,
    parsedJson: json,
    jq: firstValue({ parsed, names: ["--jq", "-q"] }),
  });
}

export function listPullRequests(context: CommandContext): CommandOutcome {
  const parsed = parseArguments({ args: context.args, valueFlags });
  const head = firstValue({ parsed, names: ["--head", "-H"] });
  const wanted = firstValue({ parsed, names: ["--state", "-s"] }) ?? "open";
  const json = firstValue({ parsed, names: ["--json"] });
  const matches = context.state.pullRequests.filter(
    (pullRequest) =>
      (head === undefined || pullRequest.head === head) &&
      (wanted === "all" || pullRequest.state.toLowerCase() === wanted.toLowerCase()),
  );
  const records = matches.map((pullRequest) => pullRequestRecord({ workspace: context.workspace, state: context.state, pullRequest }));

  return render({
    context,
    operation: "pr-list",
    value: records.map((record) => pickFields({ record, fields: json })),
    text: `${records.map((record) => `${String(record.number)}\t${String(record.title)}\t${String(record.headRefName)}\t${String(record.state)}`).join("\n")}\n`,
    parsedJson: json,
    jq: firstValue({ parsed, names: ["--jq", "-q"] }),
  });
}

export function pullRequestChecks(context: CommandContext): CommandOutcome {
  const parsed = parseArguments({ args: context.args, valueFlags: [...valueFlags, "--interval", "-i"] });
  const pullRequest = findPullRequest({ state: context.state, selector: parsed.positionals[0], cwd: context.cwd });

  if (!pullRequest) {
    return fail({ operation: "pr-checks", message: "no pull requests found for branch" });
  }

  const checks = checkRollup({ workspace: context.workspace, state: context.state, pullRequest });
  const head = remoteHead({ remoteDirectory: context.workspace.remoteDirectory, branch: pullRequest.head });
  const json = firstValue({ parsed, names: ["--json"] });
  const failing = checks.some((check) => check.bucket === "fail");
  const details = { pullRequest: pullRequest.number, head, failing, checks: checks.map((check) => ({ name: check.name, bucket: check.bucket })) };

  if (checks.length === 0) {
    return fail({ operation: "pr-checks", message: `no checks reported on the '${pullRequest.head}' branch`, details });
  }

  const outcome = render({
    context,
    operation: "pr-checks",
    value: checks.map((check) => pickFields({ record: check, fields: json })),
    text: `${checks.map((check) => `${String(check.name)}\t${String(check.bucket)}\t1m2s\t${String(check.link)}`).join("\n")}\n`,
    parsedJson: json,
    jq: firstValue({ parsed, names: ["--jq", "-q"] }),
  });

  return { ...outcome, exitCode: outcome.exitCode === 0 && failing && json === undefined ? 1 : outcome.exitCode, details };
}

export function pullRequestDiff(context: CommandContext): CommandOutcome {
  const parsed = parseArguments({ args: context.args, valueFlags });
  const pullRequest = findPullRequest({ state: context.state, selector: parsed.positionals[0], cwd: context.cwd });

  if (!pullRequest) {
    return fail({ operation: "pr-diff", message: "no pull requests found for branch" });
  }

  const result = runGit({
    cwd: context.workspace.remoteDirectory,
    args: ["diff", ...(hasSwitch({ parsed, names: ["--name-only"] }) ? ["--name-only"] : []), `${pullRequest.base}...${pullRequest.head}`],
  });

  return succeed({ operation: "pr-diff", stdout: result.stdout });
}

export function pullRequestStatus(context: CommandContext): CommandOutcome {
  const lines = context.state.pullRequests
    .filter((pullRequest) => pullRequest.state === "OPEN")
    .map((pullRequest) => {
      const record = pullRequestRecord({ workspace: context.workspace, state: context.state, pullRequest });

      return `#${pullRequest.number} ${pullRequest.title} [${pullRequest.head}] ${pullRequest.draft ? "Draft" : "Open"} ${String(record.mergeStateStatus)}`;
    });

  return succeed({ operation: "pr-status", stdout: `Created by you\n${lines.join("\n")}\n` });
}
