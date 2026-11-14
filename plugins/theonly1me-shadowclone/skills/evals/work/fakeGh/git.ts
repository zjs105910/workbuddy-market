import { appendFileSync, existsSync } from "node:fs";
import path from "node:path";

const siblingGit = path.join(path.dirname(process.execPath), "git");
const siblingExecPath = path.join(path.dirname(process.execPath), "git-core");
const gitBinary = existsSync(siblingGit) ? siblingGit : "git";
let failureLog: string | null = null;

export function logCommandFailures(file: string): void {
  failureLog = file;
}

export type CommandResult = {
  readonly exitCode: number;
  readonly stdout: string;
  readonly stderr: string;
};

export function runCommand(options: {
  readonly command: readonly string[];
  readonly cwd: string;
  readonly stdin?: string;
  readonly timeoutMs?: number;
}): CommandResult {
  const result = Bun.spawnSync({
    cmd: [...options.command],
    cwd: options.cwd,
    stdin: options.stdin === undefined ? "ignore" : Buffer.from(options.stdin),
    stdout: "pipe",
    stderr: "pipe",
    timeout: options.timeoutMs ?? 120_000,
    env: {
      ...process.env,
      GIT_EDITOR: "true",
      GIT_TERMINAL_PROMPT: "0",
      ...(existsSync(siblingExecPath) ? { GIT_EXEC_PATH: siblingExecPath } : {}),
    },
  });
  const outcome = {
    exitCode: result.exitCode ?? 1,
    stdout: result.stdout.toString(),
    stderr: result.stderr.toString(),
  };

  if (outcome.exitCode !== 0 && failureLog !== null) {
    appendFileSync(failureLog, `${JSON.stringify({ command: options.command, cwd: options.cwd, exitCode: outcome.exitCode, stderr: outcome.stderr.slice(0, 2000) })}\n`);
  }

  return outcome;
}

export function runGit(options: {
  readonly cwd: string;
  readonly args: readonly string[];
}): CommandResult {
  return runCommand({ command: [gitBinary, ...options.args], cwd: options.cwd });
}

export function remoteHead(options: {
  readonly remoteDirectory: string;
  readonly branch: string;
}): string | null {
  const result = runGit({
    cwd: options.remoteDirectory,
    args: ["rev-parse", "--verify", "--quiet", `refs/heads/${options.branch}`],
  });

  return result.exitCode === 0 ? result.stdout.trim() : null;
}

export function isAncestor(options: {
  readonly gitDirectory: string;
  readonly ancestor: string;
  readonly descendant: string;
}): boolean {
  return (
    runGit({
      cwd: options.gitDirectory,
      args: ["merge-base", "--is-ancestor", options.ancestor, options.descendant],
    }).exitCode === 0
  );
}

export function mergesCleanly(options: {
  readonly gitDirectory: string;
  readonly base: string;
  readonly head: string;
}): boolean {
  return (
    runGit({
      cwd: options.gitDirectory,
      args: ["merge-tree", "--write-tree", "--name-only", options.base, options.head],
    }).exitCode === 0
  );
}

export function currentBranch(cwd: string): string | null {
  const result = runGit({ cwd, args: ["symbolic-ref", "--quiet", "--short", "HEAD"] });

  return result.exitCode === 0 ? result.stdout.trim() : null;
}

export function changedPaths(options: {
  readonly gitDirectory: string;
  readonly base: string;
  readonly head: string;
}): readonly string[] {
  const result = runGit({
    cwd: options.gitDirectory,
    args: ["diff", "--name-only", `${options.base}...${options.head}`],
  });

  return result.stdout.split("\n").filter((line) => line.length > 0);
}

export function commitTouches(options: {
  readonly gitDirectory: string;
  readonly commit: string;
  readonly path: string;
}): boolean {
  const result = runGit({
    cwd: options.gitDirectory,
    args: ["show", "--name-only", "--format=", options.commit, "--", options.path],
  });

  return result.exitCode === 0 && result.stdout.trim().length > 0;
}
