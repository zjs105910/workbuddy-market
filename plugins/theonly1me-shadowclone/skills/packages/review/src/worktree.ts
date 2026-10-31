import { realpathSync } from "node:fs";
import { readGit } from "./collect/git";

export type Worktree = {
  readonly root: string;
  readonly roots: readonly string[];
};

export async function addWorktree(options: {
  readonly repository: string;
  readonly sha: string;
  readonly directory: string;
}): Promise<Worktree> {
  await readGit({
    checkout: options.repository,
    arguments: ["worktree", "add", "--detach", "--force", options.directory, options.sha],
  });

  return { root: options.directory, roots: [options.directory, realpathSync(options.directory)] };
}

export async function removeWorktree(options: {
  readonly repository: string;
  readonly directory: string;
}): Promise<void> {
  await readGit({
    checkout: options.repository,
    arguments: ["worktree", "remove", "--force", options.directory],
  }).catch(() => readGit({ checkout: options.repository, arguments: ["worktree", "prune"] }));
}
