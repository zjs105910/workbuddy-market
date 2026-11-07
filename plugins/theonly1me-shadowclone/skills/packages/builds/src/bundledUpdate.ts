import path from "node:path";
import type { FileUpdate } from "@shadowclone/changes";
import { readEffectiveConfig, readLocalText, acquireLocalLock } from "@shadowclone/core";
import {
  environmentFile,
  type EnvironmentState,
  publishEnvironmentRevision,
  readEnvironment,
  renderEnvironment,
} from "@shadowclone/environment";
import type { ProjectPaths } from "@shadowclone/core";
import {
  migrateAlwaysOnSkills,
  renderAlwaysOnChanges,
  type AlwaysOnChange,
} from "./alwaysOnMigration";
import { renderRetiredSkillChanges, type RetiredSkillChange } from "./retired";
import { migrateRetiredSkills } from "./retiredMigration";
import { renderBuildSkillSync, syncBuildSkills, type BuildSkillSyncReport } from "./sync";

export type BundledSkillReport = BuildSkillSyncReport & {
  readonly retired: readonly RetiredSkillChange[];
  readonly alwaysOn: readonly AlwaysOnChange[];
  readonly warnings: readonly string[];
};

async function publishState(options: {
  readonly paths: ProjectPaths;
  readonly updates: readonly FileUpdate[];
  readonly state: EnvironmentState;
}): Promise<void> {
  const filePath = environmentFile(options.paths);
  const updates = [
    ...options.updates,
    {
      filePath,
      previous: await readLocalText(filePath),
      next: renderEnvironment(options.state),
    },
  ].filter((update) => update.previous !== update.next);

  await publishEnvironmentRevision({ paths: options.paths, updates });
}

export async function updateBundledSkills(paths: ProjectPaths): Promise<BundledSkillReport | null> {
  if ((await readEnvironment(paths))?.phase !== "active") {
    return null;
  }

  const { policy } = await readEffectiveConfig({
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
      return null;
    }

    const migrated = await migrateRetiredSkills({ paths, state: current });

    await publishState({ paths, updates: migrated.updates, state: migrated.state });

    const required = await migrateAlwaysOnSkills({ paths, state: migrated.state });

    await publishState({ paths, updates: required.updates, state: required.state });

    const synced = await syncBuildSkills({ state: required.state });

    await publishState({ paths, updates: synced.updates, state: synced.state });

    return {
      updated: synced.updated,
      kept: synced.kept,
      retired: migrated.changes,
      alwaysOn: required.changes,
      warnings: [...migrated.warnings, ...required.warnings],
    };
  } finally {
    lock.release();
  }
}

export function renderBundledSkillReport(report: BundledSkillReport): readonly string[] {
  return [
    ...renderRetiredSkillChanges(report.retired),
    ...renderAlwaysOnChanges(report.alwaysOn),
    ...report.warnings,
    ...renderBuildSkillSync(report),
  ];
}
