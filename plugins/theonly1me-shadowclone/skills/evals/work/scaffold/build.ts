import { appendFileSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { runGit } from "../fakeGh/git";
import { type FakeState, workspaceFor, writeState } from "../fakeGh/state";
import type { CaseDefinition } from "./definition";

const identity = [
  "-c", "user.name=Fixture Author",
  "-c", "user.email=fixture@example.com",
  "-c", "commit.gpgsign=false",
  "-c", "init.defaultBranch=main",
];

export const firstNewPullRequest = 42;

function git(options: { readonly cwd: string; readonly args: readonly string[] }): string {
  const result = runGit({ cwd: options.cwd, args: [...identity, ...options.args] });

  if (result.exitCode !== 0) {
    throw new Error(`git ${options.args.join(" ")} failed: ${result.stderr.trim()}`);
  }

  return result.stdout.trim();
}

function writeFiles(options: { readonly root: string; readonly files: Readonly<Record<string, string | null>> }): void {
  for (const [relative, content] of Object.entries(options.files)) {
    const target = path.join(options.root, relative);

    if (content === null) {
      rmSync(target, { force: true });
    } else {
      mkdirSync(path.dirname(target), { recursive: true });
      writeFileSync(target, content);
    }
  }
}

function applySteps(options: {
  readonly cwd: string;
  readonly steps: CaseDefinition["local"];
}): void {
  for (const step of options.steps) {
    const exists = runGit({ cwd: options.cwd, args: ["rev-parse", "--verify", "--quiet", `refs/heads/${step.branch}`] }).exitCode === 0;
    const tracked = runGit({ cwd: options.cwd, args: ["rev-parse", "--verify", "--quiet", `refs/remotes/origin/${step.branch}`] }).exitCode === 0;
    const start = exists
      ? ["checkout", "--quiet", step.branch]
      : tracked
        ? ["checkout", "--quiet", "-b", step.branch, `origin/${step.branch}`]
        : ["checkout", "--quiet", "-b", step.branch, step.from ?? "main"];

    git({ cwd: options.cwd, args: start });

    for (const commit of step.commits) {
      writeFiles({ root: options.cwd, files: commit.files });
      git({ cwd: options.cwd, args: ["add", "--all"] });
      git({ cwd: options.cwd, args: ["commit", "--quiet", "-m", commit.message] });
    }
  }
}

function initialState(options: {
  readonly definition: CaseDefinition;
  readonly remoteDirectory: string;
}): FakeState {
  const head = (branch: string) => git({ cwd: options.remoteDirectory, args: ["rev-parse", `refs/heads/${branch}`] });

  return {
    repository: { owner: "acme", name: "ledger" },
    defaultBranch: "main",
    viewer: "you",
    nextId: 5000,
    nextPullRequest: firstNewPullRequest,
    pullRequests: options.definition.pullRequests.map((pullRequest) => ({
      ...pullRequest,
      state: "OPEN" as const,
      initialHead: head(pullRequest.head),
    })),
    threads: options.definition.threads.map((thread, index) => ({
      id: thread.id,
      pullRequest: thread.pullRequest,
      path: thread.path,
      line: thread.line,
      release: thread.release,
      released: thread.release === "initial",
      resolved: false,
      resolvedBy: null,
      comments: [{ id: 1000 + index, author: thread.author, bot: thread.bot, body: thread.body, createdAt: "2026-10-01T12:00:00Z" }],
    })),
    topLevelComments: [],
    jobs: options.definition.jobs,
    runs: [],
    stack: options.definition.stack === null ? null : { ...options.definition.stack, rebase: null },
  };
}

export function buildWorkspace(options: {
  readonly root: string;
  readonly definition: CaseDefinition;
}): void {
  const { root, definition } = options;
  const workspace = workspaceFor(root);

  mkdirSync(workspace.stateDirectory, { recursive: true });
  git({ cwd: root, args: ["init", "--quiet"] });
  writeFiles({ root, files: definition.files });
  git({ cwd: root, args: ["add", "--all"] });
  git({ cwd: root, args: ["commit", "--quiet", "-m", "chore: initial project"] });
  applySteps({ cwd: root, steps: definition.local });
  git({ cwd: root, args: ["init", "--quiet", "--bare", workspace.remoteDirectory] });
  git({ cwd: root, args: ["remote", "add", "origin", workspace.remoteDirectory] });
  git({ cwd: root, args: ["push", "--quiet", "origin", ...["main", ...definition.pushed].map((branch) => `${branch}:${branch}`)] });
  git({ cwd: root, args: ["fetch", "--quiet", "origin"] });

  for (const branch of ["main", ...definition.pushed]) {
    git({ cwd: root, args: ["branch", "--quiet", `--set-upstream-to=origin/${branch}`, branch] });
  }

  if (definition.upstream.length > 0) {
    const teammate = mkdtempSync(path.join(os.tmpdir(), "fake-gh-teammate-"));

    git({ cwd: teammate, args: ["clone", "--quiet", workspace.remoteDirectory, "."] });
    applySteps({ cwd: teammate, steps: definition.upstream });
    git({ cwd: teammate, args: ["push", "--quiet", "origin", ...definition.upstream.map((step) => `${step.branch}:${step.branch}`)] });
    rmSync(teammate, { recursive: true, force: true });
  }

  git({ cwd: root, args: ["checkout", "--quiet", definition.checkout] });
  git({ cwd: root, args: ["config", "user.name", "You"] });
  git({ cwd: root, args: ["config", "user.email", "you@example.com"] });
  appendFileSync(path.join(root, ".git", "info", "exclude"), "/bin/\n/.fake-gh/\n");
  writeFiles({ root: path.join(workspace.stateDirectory, "ci"), files: definition.hiddenTests });
  writeState({ workspace, state: initialState({ definition, remoteDirectory: workspace.remoteDirectory }) });
  writeFileSync(path.join(workspace.stateDirectory, "log.jsonl"), "");
}
