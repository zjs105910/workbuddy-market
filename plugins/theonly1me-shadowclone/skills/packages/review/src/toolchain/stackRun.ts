import { redactSecrets } from "@shadowclone/redact";
import type { DiffFile } from "../collect";
import type { Worktree } from "../worktree";
import { limitToChanges, subtractBase } from "./compare";
import { stackContext } from "./context";
import { parseDiagnostics } from "./parsers";
import { runTool, type ToolRun } from "./process";
import type { CommandReport, Diagnostic, Stack, StackContext, ToolCommand } from "./types";

const timeoutMilliseconds = 10 * 60_000;
const maximumDiagnostics = 50;

type Side = { readonly context: StackContext; readonly roots: readonly string[] };

function describe(run: Exclude<ToolRun, { kind: "finished" }>): string {
  if (run.kind === "missing") {
    return `${run.executable} is not installed`;
  }

  return run.kind === "timed-out" ? "timed out" : "printed more output than the limit";
}

function outputTail(output: string): string {
  return redactSecrets({ text: output.trim().slice(-600) });
}

async function prepareSide(options: {
  readonly stack: Stack;
  readonly worktree: Worktree;
  readonly changedFiles: readonly string[];
}): Promise<Side | string> {
  const context = stackContext({ root: options.worktree.root, changedFiles: options.changedFiles });
  const install = options.stack.install(context);

  if (install !== null) {
    const run = await runTool({ arguments: install, cwd: context.root, timeoutMilliseconds });

    if (run.kind !== "finished") {
      return `install ${describe(run)}`;
    }

    if (run.exitCode !== 0) {
      return `install failed: ${outputTail(run.output)}`;
    }
  }

  return { context, roots: options.worktree.roots };
}

async function diagnosticsAt(options: {
  readonly side: Side;
  readonly command: ToolCommand;
}): Promise<{ readonly diagnostics: readonly Diagnostic[] } | { readonly failure: string; readonly status: CommandReport["status"] } | null> {
  const arguments_ = options.command.command(options.side.context);

  if (arguments_ === null) {
    return null;
  }

  const run = await runTool({ arguments: arguments_, cwd: options.side.context.root, timeoutMilliseconds });

  if (run.kind !== "finished") {
    return { failure: describe(run), status: run.kind === "missing" ? "skipped" : run.kind === "timed-out" ? "timed-out" : "failed" };
  }

  const diagnostics = parseDiagnostics({
    tool: options.command.tool,
    parser: options.command.parser,
    output: run.output,
    roots: options.side.roots,
  });

  return run.exitCode !== 0 && diagnostics.length === 0
    ? { failure: outputTail(run.output), status: "failed" }
    : { diagnostics };
}

export async function runStack(options: {
  readonly stack: Stack;
  readonly head: Worktree;
  readonly base: () => Promise<Worktree>;
  readonly files: readonly DiffFile[];
  readonly onProgress: (message: string) => void;
}): Promise<readonly CommandReport[]> {
  const { stack, files } = options;
  const changedFiles = files.filter((file) => !file.deleted).map((file) => file.path);
  const report = (tool: string, status: CommandReport["status"], detail: string, diagnostics: readonly Diagnostic[] = []): CommandReport =>
    ({ stack: stack.id, tool, status, detail, diagnostics: diagnostics.slice(0, maximumDiagnostics) });

  options.onProgress(`${stack.id}: installing at the head`);
  const head = await prepareSide({ stack, worktree: options.head, changedFiles });

  if (typeof head === "string") {
    return [report("install", "failed", head)];
  }

  let baseSide: Promise<Side | string> | null = null;
  const base = () => {
    baseSide ??= options.base().then((worktree) => prepareSide({ stack, worktree, changedFiles }));
    return baseSide;
  };
  const reports: CommandReport[] = [];

  for (const command of stack.commands.filter((candidate) => candidate.command(head.context) !== null)) {
    options.onProgress(`${stack.id}: ${command.tool} at the head`);
    const atHead = await diagnosticsAt({ side: head, command });

    if (atHead === null) {
      continue;
    }

    if ("failure" in atHead) {
      reports.push(report(command.tool, atHead.status, atHead.failure));
      continue;
    }

    if (command.scope !== "new-in-head") {
      reports.push(report(command.tool, "ran", "limited to changed lines", limitToChanges({ diagnostics: atHead.diagnostics, files, scope: command.scope })));
      continue;
    }

    if (atHead.diagnostics.length === 0) {
      reports.push(report(command.tool, "ran", "no diagnostics at the head"));
      continue;
    }

    options.onProgress(`${stack.id}: ${command.tool} at the base`);
    const side = await base();
    const atBase = typeof side === "string" ? null : await diagnosticsAt({ side, command });

    if (atBase === null || "failure" in atBase) {
      const reason = typeof side === "string" ? side : atBase === null ? "not configured at the base" : atBase.failure;
      reports.push(report(command.tool, "ran", `the base could not be checked (${reason}); showing diagnostics in changed files`, limitToChanges({ diagnostics: atHead.diagnostics, files, scope: "changed-files" })));
      continue;
    }

    const added = subtractBase({ head: atHead.diagnostics, base: atBase.diagnostics });
    reports.push(report(command.tool, "ran", `${added.length} new of ${atHead.diagnostics.length} at the head`, added));
  }

  return reports;
}
