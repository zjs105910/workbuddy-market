import path from "node:path";
import { readLocalText } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";
import { mergeProfileContent, mergeReferenceContent } from "./merge";
import type {
  BlockedOriginRepair,
  OriginRepair,
  ProfileRepairPlan,
} from "./types";

async function markdownFiles(root: string): Promise<readonly string[]> {
  try {
    return (
      await Array.fromAsync(
        new Bun.Glob("**/*.md").scan({
          cwd: root,
          onlyFiles: true,
          throwErrorOnBrokenSymlink: true,
        }),
      )
    ).sort();
  } catch {
    return [];
  }
}

export async function planOrigin(options: {
  readonly paths: ProjectPaths;
  readonly sourceDirectory: string;
  readonly targetDirectory: string;
  readonly originId: string;
}): Promise<{
  readonly repair?: OriginRepair;
  readonly blocked?: BlockedOriginRepair;
  readonly updates: ProfileRepairPlan["updates"];
}> {
  const locations = [
    { root: "org", reference: false },
    { root: path.join("references", "org"), reference: true },
  ];
  const updates: ProfileRepairPlan["updates"][number][] = [];

  for (const location of locations) {
    const sourceRoot = path.join(
      options.paths.profileDirectory,
      location.root,
      options.sourceDirectory,
    );

    for (const tail of await markdownFiles(sourceRoot)) {
      const sourcePath = path.join(sourceRoot, tail);
      const targetRelativePath = path.join(
        location.root,
        options.targetDirectory,
        tail,
      );
      const targetPath = path.join(
        options.paths.profileDirectory,
        targetRelativePath,
      );
      const source = await readLocalText(sourcePath);
      const target = await readLocalText(targetPath);

      if (source === null) {
        continue;
      }

      const merged = location.reference
        ? mergeReferenceContent({
            source,
            target,
            targetDirectory: options.targetDirectory,
          })
        : mergeProfileContent({
            source,
            target,
            targetRelativePath,
            originId: options.originId,
          });

      if ("blocked" in merged) {
        return {
          blocked: {
            sourceDirectory: options.sourceDirectory,
            targetDirectory: options.targetDirectory,
            reason: merged.blocked,
          },
          updates: [],
        };
      }

      updates.push({
        filePath: targetPath,
        previous: target,
        next: merged.content,
      });
      updates.push({ filePath: sourcePath, previous: source, next: null });
    }
  }

  return {
    repair: {
      sourceDirectory: options.sourceDirectory,
      targetDirectory: options.targetDirectory,
      files: updates.length / 2,
    },
    updates,
  };
}
