import path from "node:path";
import { readLocalText, acquireLocalLock, readEffectiveConfig } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";
import { environmentFile, readEnvironment, renderEnvironment } from "./store";
import { nativePublication, type SkippedRouting } from "./native";
import { publishEnvironmentRevision } from "./revision";
import { synchronizePublishedSkills } from "./synchronize";

export async function syncLearningEnvironment(
  paths: ProjectPaths,
  options: { readonly onSkipped?: (skipped: readonly SkippedRouting[]) => void } = {},
): Promise<boolean> {
  const state = await readEnvironment(paths);

  if (state?.phase !== "active") {
    return false;
  }

  const { config, policy } = await readEffectiveConfig({
    configPath: paths.configFile,
    managedConfigPath: paths.managedConfigFile,
  });

  if (!policy.enabled) {
    throw new Error("Managed policy blocks synchronization");
  }

  const lock = await acquireLocalLock(
    path.join(paths.shadowcloneDirectory, "environment-write.db"),
  );

  if (!lock) {
    throw new Error("Another learning environment update is running");
  }

  try {
    const current = await readEnvironment(paths);

    if (current?.phase !== "active") {
      return false;
    }

    const synchronized = config.sources["skill-library"]
      ? await synchronizePublishedSkills({ paths, state: current })
      : { state: current, updates: [], routingBlocked: false };
    const publication = synchronized.routingBlocked
      ? { state: synchronized.state, updates: [], skipped: [] }
      : await nativePublication({
          paths,
          state: synchronized.state,
          skipLinkedFiles: options.onSkipped !== undefined,
        });
    const filePath = environmentFile(paths);

    await publishEnvironmentRevision({
      paths,
      updates: [
        ...synchronized.updates,
        ...publication.updates,
        {
          filePath,
          previous: await readLocalText(filePath),
          next: renderEnvironment(publication.state),
        },
      ],
    });

    options.onSkipped?.(publication.skipped);

    return true;
  } finally {
    lock.release();
  }
}
