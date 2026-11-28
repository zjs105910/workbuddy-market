import { applyJq, firstValue, hasSwitch, parseArguments, pickFields } from "./arguments";
import { rerunJobs } from "./checks";
import { type CommandContext, type CommandOutcome, fail, succeed } from "./context";
import { currentBranch, remoteHead } from "./git";
import type { CheckRun } from "./state";

const valueFlags = ["--branch", "-b", "--json", "--jq", "-q", "--limit", "-L", "--workflow", "-w", "--job", "-j", "--commit", "-c", "--status", "-s", "--repo", "-R"];

function runRecord(options: { readonly context: CommandContext; readonly run: CheckRun }): Readonly<Record<string, unknown>> {
  const branch = options.context.state.pullRequests.find(
    (pullRequest) => remoteHead({ remoteDirectory: options.context.workspace.remoteDirectory, branch: pullRequest.head }) === options.run.sha,
  )?.head;

  return {
    databaseId: options.run.id,
    name: options.run.job,
    workflowName: "ci",
    displayTitle: options.run.job,
    headSha: options.run.sha,
    headBranch: branch ?? "",
    status: "completed",
    conclusion: options.run.conclusion,
    attempt: options.run.attempt,
    url: `https://github.com/${options.context.state.repository.owner}/${options.context.state.repository.name}/actions/runs/${options.run.id}`,
  };
}

function renderJson(options: {
  readonly context: CommandContext;
  readonly operation: string;
  readonly value: unknown;
  readonly jq: string | undefined;
}): CommandOutcome {
  const rendered = applyJq({ value: options.value, expression: options.jq, cwd: options.context.cwd });

  return rendered.exitCode === 0
    ? succeed({ operation: options.operation, stdout: rendered.text })
    : fail({ operation: options.operation, message: rendered.text.trim() });
}

export function listRuns(context: CommandContext): CommandOutcome {
  const parsed = parseArguments({ args: context.args, valueFlags });
  const branch = firstValue({ parsed, names: ["--branch", "-b"] });
  const sha = branch === undefined ? undefined : remoteHead({ remoteDirectory: context.workspace.remoteDirectory, branch });
  const runs = [...context.state.runs].reverse().filter((run) => sha === undefined || run.sha === sha);
  const records = runs.map((run) => runRecord({ context, run }));
  const json = firstValue({ parsed, names: ["--json"] });

  if (json !== undefined) {
    return renderJson({ context, operation: "run-list", value: records.map((record) => pickFields({ record, fields: json })), jq: firstValue({ parsed, names: ["--jq", "-q"] }) });
  }

  return succeed({
    operation: "run-list",
    stdout: `${records.map((record) => `${String(record.conclusion)}\t${String(record.name)}\t${String(record.headBranch)}\t${String(record.databaseId)}`).join("\n")}\n`,
  });
}

export function viewRun(context: CommandContext): CommandOutcome {
  const parsed = parseArguments({ args: context.args, valueFlags });
  const run = context.state.runs.find((candidate) => String(candidate.id) === parsed.positionals[0]);

  if (!run) {
    return fail({ operation: "run-view", message: "could not find any workflow run" });
  }

  const json = firstValue({ parsed, names: ["--json"] });

  if (json !== undefined) {
    return renderJson({ context, operation: "run-view", value: pickFields({ record: runRecord({ context, run }), fields: json }), jq: firstValue({ parsed, names: ["--jq", "-q"] }) });
  }

  const logs = hasSwitch({ parsed, names: ["--log", "--log-failed"] });

  return succeed({
    operation: "run-view",
    stdout: logs ? `${run.job}\t${run.output}\n` : `${run.conclusion === "success" ? "✓" : "X"} ${run.job} · ${run.id}\nAttempt ${run.attempt}\n`,
    details: { runId: run.id, logs },
  });
}

export function rerunRun(context: CommandContext): CommandOutcome {
  const parsed = parseArguments({ args: context.args, valueFlags });
  const runId = Number(parsed.positionals[0]);

  if (!context.state.runs.some((run) => run.id === runId)) {
    return fail({ operation: "run-rerun", message: "could not find any workflow run" });
  }

  const reruns = rerunJobs({ workspace: context.workspace, state: context.state, runId, failedOnly: hasSwitch({ parsed, names: ["--failed"] }) });

  return succeed({
    operation: "run-rerun",
    stdout: `✓ Requested rerun of run ${runId}\n`,
    details: { runId, reruns: reruns.map((run) => ({ id: run.id, conclusion: run.conclusion })) },
  });
}

export function watchRun(context: CommandContext): CommandOutcome {
  const parsed = parseArguments({ args: context.args, valueFlags: [...valueFlags, "--interval", "-i"] });
  const run =
    context.state.runs.find((candidate) => String(candidate.id) === parsed.positionals[0]) ??
    [...context.state.runs].reverse().find((candidate) => candidate.sha === remoteHead({ remoteDirectory: context.workspace.remoteDirectory, branch: currentBranch(context.cwd) ?? "" }));

  if (!run) {
    return fail({ operation: "run-watch", message: "found no in progress runs to watch" });
  }

  return {
    ...succeed({ operation: "run-watch", stdout: `${run.conclusion === "success" ? "✓" : "X"} ${run.job} completed with '${run.conclusion}'\n` }),
    exitCode: run.conclusion === "success" || !hasSwitch({ parsed, names: ["--exit-status"] }) ? 0 : 1,
  };
}
