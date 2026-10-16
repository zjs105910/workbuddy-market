import type { ProjectPaths } from "@shadowclone/core";
import { readEnvironment, renderEnvironment, environmentFile } from "./store";
import { readLocalText, acquireLocalLock, readEffectiveConfig } from "@shadowclone/core";
import { publishEnvironmentRevision } from "./revision";
import path from "node:path";
import { recordFingerprint } from "./records";
import { belongsToScope, learningScopes } from "./scope";

export async function setAutomaticMaintenance(options: {
  readonly paths: ProjectPaths;
  readonly enabled: boolean;
}): Promise<void> {
  const lock = await acquireLocalLock(
    path.join(options.paths.shadowcloneDirectory, "environment-write.db"),
  );

  if (!lock) {
    throw new Error("Another learning update is running");
  }

  try {
    const state = await readEnvironment(options.paths);

    if (state === null) {
      throw new Error(
        "Run migrate skills before enabling environment maintenance",
      );
    }

    const filePath = environmentFile(options.paths);

    await publishEnvironmentRevision({
      paths: options.paths,
      updates: [
        {
          filePath,
          previous: await readLocalText(filePath),
          next: renderEnvironment({ ...state, automatic: options.enabled }),
        },
      ],
    });
  } finally {
    lock.release();
  }
}

export async function reviewLearning(options: {
  readonly paths: ProjectPaths;
  readonly key: string;
  readonly action: "retry" | "exclude";
  readonly reason?: string;
}): Promise<void> {
  const lock = await acquireLocalLock(
    path.join(options.paths.shadowcloneDirectory, "environment-write.db"),
  );

  if (!lock) {
    throw new Error("Another learning update is running");
  }

  try {
    const state = await readEnvironment(options.paths);
    const record = state?.records.find(({ rule }) => rule.key === options.key);

    if (!state || !record) {
      throw new Error("Learning record was not found");
    }
    if (options.action === "retry") {
      const { config } = await readEffectiveConfig({
        configPath: options.paths.configFile, managedConfigPath: options.paths.managedConfigFile,
      });
      const disabled = record.captureSources?.filter((source) => !config.sources[source]) ?? [];
      if (disabled.length > 0) throw new Error(`Learned rule uses disabled sources: ${disabled.join(", ")}`);
    }

    if (options.action === "exclude" && !options.reason?.trim()) {
      throw new Error("Excluding learning requires an explicit reason");
    }

    const dispositions = state.dispositions.filter(
      (entry) => entry.key !== options.key,
    );

    if (options.action === "exclude") {
      for (const scope of learningScopes({
        paths: options.paths,
        state,
      }).filter((scope) => belongsToScope({ record, scope }))) {
        dispositions.push({
          key: options.key,
          scope: scope.key,
          inputFingerprint: recordFingerprint(record),
          status: "excluded",
          reason: options.reason ?? "",
          destinations: [],
        });
      }
    }

    const filePath = environmentFile(options.paths);

    await publishEnvironmentRevision({
      paths: options.paths,
      updates: [
        {
          filePath,
          previous: await readLocalText(filePath),
          next: renderEnvironment({ ...state, dispositions }),
        },
      ],
    });
  } finally {
    lock.release();
  }
}
