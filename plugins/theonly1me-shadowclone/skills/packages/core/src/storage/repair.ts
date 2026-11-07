import { chmod, lstat, readdir } from "node:fs/promises";
import path from "node:path";
import { ownedDirectoryMode, ownedFileMode } from "./write";

export type RepairSummary = {
  readonly directories: number;
  readonly files: number;
  readonly skipped: number;
};

function isMissing(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "code" in error &&
    (error.code === "ENOENT" || error.code === "ENOTDIR")
  );
}

async function repairEntry(options: {
  readonly entryPath: string;
  readonly root: string;
  readonly summary: { directories: number; files: number; skipped: number };
}): Promise<void> {
  const stats = await lstat(options.entryPath);

  if (stats.isDirectory()) {
    if ((stats.mode & 0o777) !== ownedDirectoryMode) {
      await chmod(options.entryPath, ownedDirectoryMode);
      options.summary.directories += 1;
    }

    if (options.entryPath === path.join(options.root, "worktrees")) {
      options.summary.skipped += 1;

      return;
    }

    const entries = await readdir(options.entryPath);

    for (const entry of entries) {
      await repairEntry({
        entryPath: path.join(options.entryPath, entry),
        root: options.root,
        summary: options.summary,
      });
    }

    return;
  }

  if (!stats.isFile()) {
    options.summary.skipped += 1;

    return;
  }

  if ((stats.mode & 0o777) !== ownedFileMode) {
    await chmod(options.entryPath, ownedFileMode);
    options.summary.files += 1;
  }
}

export async function repairOwnedTree(root: string): Promise<RepairSummary> {
  const summary = { directories: 0, files: 0, skipped: 0 };

  try {
    await repairEntry({ entryPath: root, root, summary });
  } catch (error) {
    if (!isMissing(error)) {
      throw error;
    }
  }

  return summary;
}
