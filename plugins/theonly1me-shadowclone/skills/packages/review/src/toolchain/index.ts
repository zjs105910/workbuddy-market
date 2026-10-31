import path from "node:path";
import type { DiffFile } from "../collect";
import { addWorktree, removeWorktree, type Worktree } from "../worktree";
import { stackContext } from "./context";
import { runStack } from "./stackRun";
import { allStacks } from "./stacks";
import type { CommandReport } from "./types";

export type { CommandReport, Diagnostic } from "./types";

export async function runToolchain(options: {
  readonly repository: string;
  readonly baseSha: string;
  readonly headSha: string;
  readonly files: readonly DiffFile[];
  readonly workDirectory: string;
  readonly onProgress: (message: string) => void;
}): Promise<readonly CommandReport[]> {
  const { repository, files } = options;
  const headDirectory = path.join(options.workDirectory, "toolchain-head");
  const baseDirectory = path.join(options.workDirectory, "toolchain-base");
  const head = await addWorktree({ repository, sha: options.headSha, directory: headDirectory });
  let base: Promise<Worktree> | null = null;

  try {
    const context = stackContext({
      root: head.root,
      changedFiles: files.filter((file) => !file.deleted).map((file) => file.path),
    });
    const stacks = allStacks.filter(
      (stack) => files.some((file) => stack.sources.test(file.path)) && stack.detect(context),
    );
    const reports: CommandReport[] = [];

    for (const stack of stacks) {
      reports.push(
        ...(await runStack({
          stack,
          head,
          base: () => {
            base ??= addWorktree({ repository, sha: options.baseSha, directory: baseDirectory });
            return base;
          },
          files,
          onProgress: options.onProgress,
        })),
      );
    }

    return reports;
  } finally {
    await removeWorktree({ repository, directory: headDirectory });

    if (base !== null) {
      await removeWorktree({ repository, directory: baseDirectory });
    }
  }
}
