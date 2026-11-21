import path from "node:path";
import type { FileUpdate } from "@shadowclone/changes";
import { readLocalText } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";
import { parseProfileBlocks } from "../../profile";
import { parseProfileRejectionText } from "../../profile";
import type { ProfileRejection } from "../../profile";
import { renderProfileRejections } from "../../profile/stateRender";

export async function appendProfileRules(options: {
  readonly paths: ProjectPaths;
  readonly rules: readonly {
    readonly relativePath: string;
    readonly key: string;
    readonly content: string;
  }[];
}): Promise<readonly FileUpdate[]> {
  const grouped = Map.groupBy(options.rules, (rule) => rule.relativePath);
  const updates: FileUpdate[] = [];

  for (const [relativePath, rules] of grouped) {
    const filePath = path.join(options.paths.profileDirectory, relativePath);
    const previous = await readLocalText(filePath);
    const blocks = previous === null ? [] : parseProfileBlocks(previous);
    const additions: string[] = [];

    for (const rule of rules) {
      const existing = blocks.find((block) => block.key === rule.key);

      if (existing && existing.content !== rule.content) {
        throw new Error(
          "Claude memory rule conflicts with an existing profile rule",
        );
      }

      if (!existing) {
        additions.push(rule.content);
      }
    }

    const content = [previous?.trim(), ...additions]
      .filter(Boolean)
      .join("\n\n");

    updates.push({
      filePath,
      previous,
      next: content.length === 0 ? null : `${content}\n`,
    });
  }

  return updates;
}

export async function mergeRejections(options: {
  readonly paths: ProjectPaths;
  readonly rejections: readonly ProfileRejection[];
}): Promise<FileUpdate | null> {
  if (options.rejections.length === 0) {
    return null;
  }

  const filePath = options.paths.rejectedProfileFile;
  const previous = await readLocalText(filePath);
  const existing = previous === null ? [] : parseProfileRejectionText(previous);
  const entries = new Map(existing.map((entry) => [entry.key, entry]));

  for (const rejection of options.rejections) {
    const current = entries.get(rejection.key);

    if (current && JSON.stringify(current) !== JSON.stringify(rejection)) {
      throw new Error(
        "Claude memory rejection conflicts with existing profile state",
      );
    }

    entries.set(rejection.key, rejection);
  }

  return {
    filePath,
    previous,
    next: renderProfileRejections([...entries.values()]),
  };
}
