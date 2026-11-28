import { hasSwitch, parseArguments } from "./arguments";
import { type CommandContext, type CommandOutcome, fail, succeed, unsupported } from "./context";
import { currentBranch, runGit } from "./git";
import { refresh } from "./pullRequests";
import type { FakeState } from "./state";

type Stack = NonNullable<FakeState["stack"]>;

function parentOf(options: { readonly stack: Stack; readonly index: number }): string {
  return options.index === 0 ? `origin/${options.stack.trunk}` : (options.stack.branches[options.index - 1] ?? options.stack.trunk);
}

function rebaseFrom(options: {
  readonly context: CommandContext;
  readonly stack: Stack;
  readonly start: number;
  readonly oldBases: Readonly<Record<string, string>>;
}): CommandOutcome {
  for (let index = options.start; index < options.stack.branches.length; index += 1) {
    const branch = options.stack.branches[index] ?? "";
    const oldBase = options.oldBases[branch] ?? parentOf({ stack: options.stack, index });
    const result = runGit({ cwd: options.context.cwd, args: ["rebase", "--onto", parentOf({ stack: options.stack, index }), oldBase, branch] });

    if (result.exitCode !== 0) {
      options.stack.rebase = { index, parentTips: { ...options.oldBases } };

      return fail({
        operation: "stack-rebase-conflict",
        message: `${result.stdout}${result.stderr}\nRebase of ${branch} stopped on a conflict.\nResolve the conflicts, stage the files with \`git add\`, then run \`gh stack rebase --continue\`.\nTo cancel, run \`gh stack rebase --abort\`.`,
        details: { branch },
      });
    }
  }

  options.stack.rebase = null;

  return succeed({
    operation: "stack-rebase",
    stdout: `✓ Rebased ${options.stack.branches.length} branches: ${options.stack.branches.join(" <- ")}\nRun \`gh stack push\` to update the remote.\n`,
    details: { branches: options.stack.branches },
  });
}

function startRebase(options: { readonly context: CommandContext; readonly stack: Stack }): CommandOutcome {
  if (options.stack.rebase !== null) {
    return fail({ operation: "stack-rebase", message: "a stack rebase is already in progress; run `gh stack rebase --continue` or `--abort`" });
  }

  const original = currentBranch(options.context.cwd);

  runGit({ cwd: options.context.cwd, args: ["fetch", "origin"] });

  const oldBases = Object.fromEntries(
    options.stack.branches.map((branch, index) => [
      branch,
      runGit({ cwd: options.context.cwd, args: ["merge-base", branch, index === 0 ? options.stack.trunk : (options.stack.branches[index - 1] ?? "")] }).stdout.trim(),
    ]),
  );
  const outcome = rebaseFrom({ context: options.context, stack: options.stack, start: 0, oldBases });

  if (outcome.exitCode === 0 && original !== null) {
    runGit({ cwd: options.context.cwd, args: ["checkout", "--quiet", original] });
  }

  return outcome;
}

function continueRebase(options: { readonly context: CommandContext; readonly stack: Stack }): CommandOutcome {
  const progress = options.stack.rebase;

  if (progress === null) {
    return fail({ operation: "stack-rebase", message: "no stack rebase is in progress" });
  }

  const result = runGit({ cwd: options.context.cwd, args: ["rebase", "--continue"] });

  if (result.exitCode !== 0) {
    return fail({ operation: "stack-rebase-conflict", message: `${result.stdout}${result.stderr}\nResolve the remaining conflicts, then run \`gh stack rebase --continue\` again.` });
  }

  return rebaseFrom({ context: options.context, stack: options.stack, start: progress.index + 1, oldBases: progress.parentTips });
}

function pushStack(options: { readonly context: CommandContext; readonly stack: Stack }): CommandOutcome {
  const results = options.stack.branches.map((branch) => ({
    branch,
    result: runGit({ cwd: options.context.cwd, args: ["push", "--force-with-lease", "origin", branch] }),
  }));
  const failed = results.filter((entry) => entry.result.exitCode !== 0);

  refresh({ workspace: options.context.workspace, state: options.context.state });

  if (failed.length > 0) {
    return fail({
      operation: "stack-push",
      message: failed.map((entry) => `${entry.branch}: ${entry.result.stderr.trim()}`).join("\n"),
      details: { failed: failed.map((entry) => entry.branch) },
    });
  }

  return succeed({ operation: "stack-push", stdout: `✓ Pushed ${results.length} branches\n`, details: { branches: options.stack.branches } });
}

function viewStack(options: { readonly context: CommandContext; readonly stack: Stack }): CommandOutcome {
  const current = currentBranch(options.context.cwd);
  const lines = [...options.stack.branches].reverse().map((branch) => {
    const pullRequest = options.context.state.pullRequests.find((candidate) => candidate.head === branch);

    return `${branch === current ? "*" : " "} ${branch}${pullRequest ? ` (#${pullRequest.number})` : ""}`;
  });

  return succeed({ operation: "stack-view", stdout: `${lines.join("\n")}\n  ${options.stack.trunk} (trunk)\n` });
}

export function stackCommand(context: CommandContext): CommandOutcome {
  const stack = context.state.stack;
  const [subcommand, ...rest] = context.args;

  if (stack === null) {
    return fail({ operation: "stack", message: "not in a stack; run `gh stack init` first" });
  }

  const parsed = parseArguments({ args: rest, valueFlags: [] });

  if (subcommand === "view" || subcommand === "status" || subcommand === "ls") {
    return viewStack({ context, stack });
  }

  if (subcommand === "rebase" && hasSwitch({ parsed, names: ["--abort"] })) {
    runGit({ cwd: context.cwd, args: ["rebase", "--abort"] });
    stack.rebase = null;

    return succeed({ operation: "stack-rebase-abort", stdout: "Stack rebase aborted\n" });
  }

  if (subcommand === "rebase") {
    return hasSwitch({ parsed, names: ["--continue"] }) ? continueRebase({ context, stack }) : startRebase({ context, stack });
  }

  if (subcommand === "push" || subcommand === "submit") {
    return pushStack({ context, stack });
  }

  if (subcommand === "sync") {
    const rebased = startRebase({ context, stack });

    return rebased.exitCode === 0 ? pushStack({ context, stack }) : rebased;
  }

  return unsupported(["stack", ...context.args]);
}
