import { runHostCommand } from "@shadowclone/core";
import { lstat, realpath } from "node:fs/promises";
import path from "node:path";

export type GitTopLevelReader = (directory: string) => Promise<string | null>;

async function readGitTopLevel(directory: string): Promise<string | null> {
  const { exitCode, stdout } = await runHostCommand({
    arguments: ["git", "rev-parse", "--show-toplevel"],
    cwd: directory,
  });
  const value = stdout.trim();

  return exitCode === 0 && value.length > 0 ? value : null;
}

export async function resolveInstallTarget(options: {
  readonly directory: string;
  readonly readTopLevel?: GitTopLevelReader;
}): Promise<string | null> {
  if (!path.isAbsolute(options.directory)) {
    return null;
  }

  const resolved = await realpath(options.directory).catch(() => null);

  if (resolved === null) {
    return null;
  }

  const readTopLevel = options.readTopLevel ?? readGitTopLevel;
  const topLevel = await readTopLevel(resolved);

  if (topLevel === null) {
    return null;
  }

  const resolvedTopLevel = await realpath(topLevel).catch(() => null);

  return resolvedTopLevel === resolved ? resolved : null;
}

export async function resolveArtifactPath(options: {
  readonly root: string;
  readonly relativePath: string;
}): Promise<string | null> {
  const segments = options.relativePath.split(path.sep).filter(Boolean);

  if (segments.length === 0) {
    return null;
  }

  let current = options.root;

  for (const segment of segments) {
    if (segment === "." || segment === "..") {
      return null;
    }

    current = path.join(current, segment);

    const stats = await lstat(current).catch(() => null);

    if (stats?.isSymbolicLink()) {
      return null;
    }
  }

  return current.startsWith(`${options.root}${path.sep}`) ? current : null;
}
