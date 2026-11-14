import { contentParts, kindFromFilename, kindFromType } from "./content";
import { lstat, readdir } from "node:fs/promises";
import path from "node:path";
import {
  readBoundedFile,
  canonicalPath,
  type ProjectPaths,
  assertRegularDestination,
} from "@shadowclone/core";
import { resolveRedacted } from "@shadowclone/sessions";
import type { ClaudeMemoryFile } from "./types";

export const maximumClaudeMemoryFiles = 256;

export const maximumClaudeMemoryBytes = 2 * 1024 * 1024;

export function claudeMemoryDirectory(options: {
  readonly paths: ProjectPaths;
  readonly repositoryRoot: string;
}): string {
  const encoded = path
    .resolve(options.repositoryRoot)
    .replaceAll(/[^a-zA-Z0-9]/g, "-");

  return path.join(options.paths.claudeProjectsDirectory, encoded, "memory");
}

export async function scanClaudeMemory(options: {
  readonly paths: ProjectPaths;
  readonly repositoryRoot: string;
}): Promise<readonly ClaudeMemoryFile[]> {
  const directory = claudeMemoryDirectory(options);

  assertRegularDestination(
    path.join(
      canonicalPath(options.paths.claudeProjectsDirectory),
      path.relative(options.paths.claudeProjectsDirectory, directory),
      "MEMORY.md",
    ),
  );

  return scanClaudeMemoryDirectory(directory);
}

export async function scanClaudeMemoryDirectory(
  directory: string,
): Promise<readonly ClaudeMemoryFile[]> {
  assertRegularDestination(
    path.join(
      canonicalPath(path.dirname(directory)),
      path.basename(directory),
      "MEMORY.md",
    ),
  );

  const entries = await readdir(directory, { withFileTypes: true }).catch(
    () => [],
  );

  if (entries.some((entry) => entry.isSymbolicLink())) {
    throw new Error("Claude memory contains a symbolic link");
  }

  if (entries.some((entry) => !entry.isFile() || !entry.name.endsWith(".md"))) {
    throw new Error("Claude memory contains an unsupported file");
  }

  const markdown = entries.filter(
    (entry) => entry.isFile() && entry.name.endsWith(".md"),
  );

  if (markdown.length > maximumClaudeMemoryFiles) {
    throw new Error("Claude memory exceeds the 256-file migration limit");
  }

  const files: ClaudeMemoryFile[] = [];
  let totalBytes = 0;

  for (const entry of markdown.sort((left, right) =>
    left.name.localeCompare(right.name),
  )) {
    const sourcePath = path.join(directory, entry.name);
    const metadata = await lstat(sourcePath);

    if (!metadata.isFile() || metadata.isSymbolicLink()) {
      throw new Error("Claude memory contains an unsupported file");
    }

    totalBytes += metadata.size;

    if (totalBytes > maximumClaudeMemoryBytes) {
      throw new Error("Claude memory exceeds the 2 MiB migration limit");
    }

    const raw = await readBoundedFile({
      filePath: sourcePath,
      roots: [directory],
      maximumBytes: maximumClaudeMemoryBytes,
    });

    if (raw === null) {
      throw new Error("Claude memory changed during migration scan");
    }

    const hash = new Bun.CryptoHasher("sha256").update(raw).digest("hex");

    const redacted = await resolveRedacted({
      ref: {
        type: "file",
        sourcePath,
        byteOffset: 0,
        byteLength: metadata.size,
        contentHash: hash,
      },
      roots: [directory],
    });

    const { type, ...parts } = contentParts(redacted);
    const fileKind = kindFromFilename(entry.name) ?? kindFromType(type);

    if (fileKind === null) {
      throw new Error(
        "Claude memory contains a file without a known memory type",
      );
    }

    files.push({
      filename: entry.name,
      sourcePath,
      kind: fileKind,
      hash,
      bytes: metadata.size,
      ...parts,
    });
  }

  return files;
}
