import path from "node:path";
import type { ProjectPaths } from "@shadowclone/core";
import type { ClaudeMemoryManifest } from "./types";

export function manifestPath(options: {
  readonly paths: ProjectPaths;
  readonly repositoryId: string;
}): string {
  const digest = new Bun.CryptoHasher("sha256")
    .update(options.repositoryId)
    .digest("hex")
    .slice(0, 16);

  return path.join(
    options.paths.profileDirectory,
    "migrations",
    `claude-memory-${digest}.json`,
  );
}

export function sameSource(options: {
  readonly stored: ClaudeMemoryManifest;
  readonly repositoryId: string;
  readonly files: readonly {
    readonly filename: string;
    readonly hash: string;
  }[];
}): boolean {
  const stored = options.stored.files
    .map((file) => `${file.filename}:${file.hash}`)
    .sort()
    .join("\n");
  const current = options.files
    .map((file) => `${file.filename}:${file.hash}`)
    .sort()
    .join("\n");

  return (
    options.stored.repositoryId === options.repositoryId && stored === current
  );
}
