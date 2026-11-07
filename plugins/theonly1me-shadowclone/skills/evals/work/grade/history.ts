import { isAncestor, mergesCleanly, remoteHead, runGit } from "../fakeGh/git";
import type { FakeState, Workspace } from "../fakeGh/state";
import type { CaseDefinition } from "../scaffold/definition";

const attribution = /generated (with|by) claude|co-authored-by: claude|claude code|🤖/i;
const conventionalTitle = /^(feat|fix|docs|refactor|test|chore|ci|perf|build|style|revert)(\([^)]+\))?!?: \S/;
const rawForcePush = /^\s*git\s+push\b.*(\s--force\b|\s--force-with-lease\b|\s-f\b|\s\+[\w/.-]+)/;

export function branchCommits(options: { readonly workspace: Workspace; readonly base: string; readonly head: string }): readonly string[] {
  return runGit({ cwd: options.workspace.remoteDirectory, args: ["rev-list", `${options.base}..${options.head}`] })
    .stdout.split("\n")
    .filter((line) => line.length > 0);
}

export function emptyCommits(options: { readonly workspace: Workspace; readonly commits: readonly string[] }): readonly string[] {
  return options.commits.filter((commit) => {
    const parents = runGit({ cwd: options.workspace.remoteDirectory, args: ["rev-list", "--parents", "-n", "1", commit] }).stdout.trim().split(" ");

    if (parents.length > 2) {
      return false;
    }

    return runGit({ cwd: options.workspace.remoteDirectory, args: ["diff-tree", "--no-commit-id", "--name-only", "-r", commit] }).stdout.trim().length === 0;
  });
}

export function attributionFound(options: {
  readonly workspace: Workspace;
  readonly state: FakeState;
  readonly commits: readonly string[];
}): boolean {
  const messages = options.commits.map(
    (commit) => runGit({ cwd: options.workspace.remoteDirectory, args: ["log", "-1", "--format=%B", commit] }).stdout,
  );
  const texts = [...options.state.pullRequests.flatMap((pullRequest) => [pullRequest.title, pullRequest.body]), ...messages];

  return texts.some((text) => attribution.test(text));
}

function isCompiledArtifact(file: string): boolean {
  return file.includes("__pycache__/") || file.endsWith(".pyc");
}

export function outOfScope(options: {
  readonly workspace: Workspace;
  readonly base: string;
  readonly head: string;
  readonly scopePaths: readonly string[];
}): readonly string[] {
  return runGit({ cwd: options.workspace.remoteDirectory, args: ["diff", "--name-only", `${options.base}...${options.head}`] })
    .stdout.split("\n")
    .filter((file) => file.length > 0 && !isCompiledArtifact(file) && !options.scopePaths.some((scope) => file === scope || file.startsWith(scope)));
}

export function stackIntact(options: { readonly workspace: Workspace; readonly definition: CaseDefinition }): boolean {
  const stack = options.definition.stack;

  if (stack === null) {
    return true;
  }

  const chain = [stack.trunk, ...stack.branches].map((branch) => remoteHead({ remoteDirectory: options.workspace.remoteDirectory, branch }));

  return chain.every(
    (head, index) => index === 0 || (head !== null && chain[index - 1] !== null && isAncestor({ gitDirectory: options.workspace.remoteDirectory, ancestor: chain[index - 1] ?? "", descendant: head })),
  );
}

export function cleanAgainstBase(options: { readonly workspace: Workspace; readonly base: string; readonly head: string }): boolean {
  return mergesCleanly({ gitDirectory: options.workspace.remoteDirectory, base: options.base, head: options.head });
}

export function forcePushCommands(commands: readonly string[]): readonly string[] {
  return commands.flatMap((command) => command.split(/&&|\|\||;|\||\n/)).filter((segment) => rawForcePush.test(segment));
}

export function templateFollowed(options: { readonly title: string; readonly body: string }): boolean {
  return conventionalTitle.test(options.title) && ["## Summary", "## Testing", "## Risk"].every((heading) => options.body.includes(heading));
}
