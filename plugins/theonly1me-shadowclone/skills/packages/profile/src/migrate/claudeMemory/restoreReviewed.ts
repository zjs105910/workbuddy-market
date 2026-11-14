import path from "node:path";
import { commitLocalChanges, type FileUpdate } from "@shadowclone/changes";
import { readLocalText, acquireLocalLock } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";
import { parseProfileBlocks } from "../../profile/parse";
import { profileRulePath, renderProfileRule } from "../../profile/render";
import {
  readGeneratedProfileState,
  readProfileRejections,
} from "../../profile/state";
import {
  renderGeneratedProfileState,
  renderProfileRejections,
} from "../../profile/stateRender";
import type { ProfileRule } from "../../profile/types";

export async function restoreReviewedMemoryRules(options: {
  readonly paths: ProjectPaths;
  readonly rules: readonly ProfileRule[];
}): Promise<string | null> {
  const lock = await acquireLocalLock(
    path.join(options.paths.shadowcloneDirectory, "profile-write.db"),
  );

  if (!lock) {
    throw new Error("Another profile update is running");
  }

  try {
    const rejections = await readProfileRejections(
      options.paths.rejectedProfileFile,
    );
    const generated = await readGeneratedProfileState(
      options.paths.profileManifestFile,
    );
    const files = new Map<string, { previous: string | null; next: string }>();

    for (const rule of options.rules) {
      const rejected = rejections.find((entry) => entry.key === rule.key);

      if (rejected?.reason !== "skill-covered") {
        throw new Error(
          "Restoration requires a reviewed skill-covered rejection",
        );
      }

      if (rule.source !== "user" || !rule.key.startsWith("claude-memory:")) {
        throw new Error(
          "Restoration requires a sourced Claude memory preference",
        );
      }

      if (profileRulePath(rule) !== rejected.relativePath) {
        throw new Error("Restoration cannot change the source scope");
      }

      const filePath = path.join(
        options.paths.profileDirectory,
        rejected.relativePath,
      );
      const previous = await readLocalText(filePath);

      if (
        previous &&
        parseProfileBlocks(previous).some((block) => block.key === rule.key)
      ) {
        throw new Error("Restoration conflicts with existing guidance");
      }

      const staged = files.get(filePath);
      const text = staged?.next ?? previous ?? "";

      files.set(filePath, {
        previous,
        next: `${text.trimEnd()}\n\n${renderProfileRule(rule)}\n`.trimStart(),
      });
    }

    const restored = new Set(options.rules.map((rule) => rule.key));
    const updates: FileUpdate[] = [...files].map(([filePath, content]) => ({
      filePath,
      ...content,
    }));

    updates.push({
      filePath: options.paths.rejectedProfileFile,
      previous: await readLocalText(options.paths.rejectedProfileFile),
      next: renderProfileRejections(
        rejections.filter((entry) => !restored.has(entry.key)),
      ),
    });
    updates.push({
      filePath: options.paths.profileManifestFile,
      previous: await readLocalText(options.paths.profileManifestFile),
      next: renderGeneratedProfileState([
        ...generated.filter((entry) => !restored.has(entry.key)),
        ...options.rules.map((rule) => {
          const rejected = rejections.find((entry) => entry.key === rule.key);

          if (!rejected) {
            throw new Error("Restoration source is unavailable");
          }

          return {
            relativePath: rejected.relativePath,
            key: rule.key,
            title: rule.title,
            body: rule.body,
            source: rule.source,
            importReference: rule.importReference,
            disposition: "present" as const,
          };
        }),
      ]),
    });

    return await commitLocalChanges({
      paths: options.paths,
      root: options.paths.profileDirectory,
      kind: "profile",
      updates,
    });
  } finally {
    lock.release();
  }
}
