import path from "node:path";
import { readLocalText } from "@shadowclone/core";
import { parseProfileBlocks } from "./parse";
import type { ExistingProfileBlock, ExistingProfileRule } from "./types";

export type ProfileFile = {
  readonly relativePath: string;
  readonly filePath: string;
  readonly blocks: readonly ExistingProfileBlock[];
  readonly content: string | null;
};

const profileRoots = new Set(["global", "org"]);

export function isProfileRelativePath(value: string): boolean {
  const segments = value.split("/");

  return (
    !value.includes("\\") &&
    profileRoots.has(segments[0] ?? "") &&
    segments.length > 1 &&
    segments.every(
      (segment) => segment.length > 0 && segment !== "." && segment !== "..",
    )
  );
}

async function readProfileFile(options: {
  readonly profileDirectory: string;
  readonly relativePath: string;
}): Promise<ProfileFile> {
  if (!isProfileRelativePath(options.relativePath)) {
    throw new Error("Profile state contains an invalid relative path");
  }

  const filePath = path.join(options.profileDirectory, options.relativePath);
  const content = await readLocalText(filePath);
  const blocks = content === null ? [] : parseProfileBlocks(content);

  return { relativePath: options.relativePath, filePath, blocks, content };
}

export function readProfileFiles(options: {
  readonly profileDirectory: string;
  readonly relativePaths: readonly string[];
}): Promise<readonly ProfileFile[]> {
  return Promise.all(
    options.relativePaths.map((relativePath) =>
      readProfileFile({
        profileDirectory: options.profileDirectory,
        relativePath,
      }),
    ),
  );
}

export function findProfileRule(
  files: readonly ProfileFile[],
  key: string,
): {
  readonly relativePath: string;
  readonly rule: ExistingProfileRule;
} | null {
  for (const file of files) {
    const rule = file.blocks.find((block) => block.key === key);

    if (rule && rule.key !== null) {
      return { relativePath: file.relativePath, rule };
    }
  }

  return null;
}
