import path from "node:path";
import { readEffectiveConfig, readLocalText, acquireLocalLock } from "@shadowclone/core";
import {
  type BuildContext,
  ensureHookRunner,
  publishEnvironmentRevision,
} from "@shadowclone/environment";
import type { BuildPlan } from "./types";

export async function applyBuild(
  options: BuildContext & { readonly plan: BuildPlan },
): Promise<string | null> {
  const lock = await acquireLocalLock(
    path.join(options.paths.shadowcloneDirectory, "environment-write.db"),
  );

  if (!lock) {
    throw new Error("Another environment update is running; retry shortly");
  }

  try {
    const { policy } = await readEffectiveConfig({
      configPath: options.paths.configFile,
      managedConfigPath: options.paths.managedConfigFile,
    });

    if (!policy.enabled) {
      throw new Error("Managed policy disables build changes");
    }

    for (const observed of options.plan.observed) {
      if ((await readLocalText(observed.filePath)) !== observed.text) {
        throw new Error(
          "The build changed after preview; review a fresh preview before applying",
        );
      }
    }

    if (options.plan.updates.some(update => update.filePath.endsWith("/extensions/shadowclone.js"))) {
      await ensureHookRunner({ paths: options.paths });
    }

    return await publishEnvironmentRevision({
      paths: options.paths,
      updates: options.plan.updates,
      state: options.plan.state,
    });
  } finally {
    lock.release();
  }
}
