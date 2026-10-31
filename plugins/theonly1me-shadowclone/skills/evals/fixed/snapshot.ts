import path from "node:path";
import { lstat, readlink } from "node:fs/promises";
import { runCommand, fingerprint, canonicalPath } from "@shadowclone/core";

export type WorkspaceSnapshot = {
  readonly head: string;
  readonly branch: string;
  readonly fingerprint: string;
  readonly contentFingerprint: string;
  readonly files: Readonly<Record<string, string>>;
  readonly dirty: boolean;
};

async function repositoryCommand(options: {
  readonly cwd: string;
  readonly command: readonly string[];
}): Promise<string> {
  const result = await runCommand({ command: options.command, cwd: options.cwd });
  if (result.exitCode !== 0) throw new Error("Task repository command failed");
  return result.stdout;
}

export async function snapshotWorkspace(
  options: { readonly cwd: string },
): Promise<WorkspaceSnapshot> {
  const [head, branch, listed, index, status] = await Promise.all([
    repositoryCommand({ cwd: options.cwd, command: ["git", "rev-parse", "HEAD"] }),
    repositoryCommand({ cwd: options.cwd, command: ["git", "branch", "--show-current"] }),
    repositoryCommand({
      cwd: options.cwd,
      command: [
        "git",
        "ls-files",
        "-z",
        "--cached",
        "--others",
        "--exclude-standard",
      ],
    }),
    repositoryCommand({ cwd: options.cwd, command: ["git", "ls-files", "--stage", "-z"] }),
    repositoryCommand({
      cwd: options.cwd,
      command: [
        "git",
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
      ],
    }),
  ]);
  const names = [...new Set(listed.split("\0").filter(Boolean))].sort();
  if (names.length > 20_000)
    throw new Error("Task snapshot exceeds the file budget");
  const files: Record<string, string> = {};
  let bytes = 0;
  for (const name of names) {
    const target = path.resolve(options.cwd, name);
    if (!target.startsWith(`${path.resolve(options.cwd)}${path.sep}`))
      throw new Error("Task snapshot encountered an invalid path");
    const metadata = await lstat(target).catch(() => null);
    if (metadata === null) {
      files[name] = fingerprint("deleted");
      continue;
    }
    if (metadata.isSymbolicLink()) {
      files[name] = fingerprint(`link:${await readlink(target)}`);
      continue;
    }
    if (
      !canonicalPath(target).startsWith(
        `${canonicalPath(options.cwd)}${path.sep}`,
      )
    )
      throw new Error(
        "Task snapshot cannot follow a directory outside the worktree",
      );
    if (!metadata.isFile())
      throw new Error(
        "Task snapshots require regular files; submodules need separate tasks",
      );
    bytes += metadata.size;
    if (metadata.size > 8_000_000 || bytes > 64_000_000)
      throw new Error("Task snapshot exceeds the byte budget");
    const content = await Bun.file(target).arrayBuffer();
    files[name] = new Bun.CryptoHasher("sha256")
      .update(String(metadata.mode & 0o777))
      .update(content)
      .digest("hex");
  }
  const contentFingerprint = fingerprint(JSON.stringify(files));
  return {
    head: head.trim(),
    branch: branch.trim(),
    contentFingerprint,
    files,
    dirty: status.length > 0,
    fingerprint: fingerprint(
      JSON.stringify([
        head.trim(),
        branch.trim(),
        contentFingerprint,
        index,
        status,
      ]),
    ),
  };
}
