import path from "node:path";
import { maximumProfileBytes } from "@shadowclone/core";
import { materializeSnapshot } from "@shadowclone/redact";
import { parseProfileBlocks } from "./parse";

export type ProfileDiagnostics = {
  readonly isolatedRules: number;
  readonly legacyRules: number;
};

export async function readProfileDiagnostics(
  profileDirectory: string,
): Promise<ProfileDiagnostics> {
  const relativePaths = await Array.fromAsync(
    new Bun.Glob("{global,org}/**/*.md").scan({
      cwd: profileDirectory,
      onlyFiles: true,
    }),
  ).catch(() => []);

  let isolatedRules = 0;
  let legacyRules = 0;

  for (const relativePath of relativePaths) {
    const snapshot = await materializeSnapshot({
      filePath: path.join(profileDirectory, relativePath),
      roots: [profileDirectory],
      maximumBytes: maximumProfileBytes,
      parse: parseProfileBlocks,
    });

    if (snapshot === null) {
      continue;
    }

    for (const block of snapshot.parsed) {
      if (block.key === null) {
        continue;
      }

      if (relativePath.startsWith(`org${path.sep}isolated--`)) {
        isolatedRules += 1;
      }

      if (block.legacy) {
        legacyRules += 1;
      }
    }
  }

  return { isolatedRules, legacyRules };
}
