import { applyAssessedSkills, nextSkillBatch } from "./assessmentBatch";
import path from "node:path";
import { readEffectiveConfig, acquireLocalLock } from "@shadowclone/core";
import type { LearningExecution } from "@shadowclone/agents";
import { compileContext } from "@shadowclone/environment";
import type { ProjectPaths } from "@shadowclone/core";
import type { GitRemoteReader } from "@shadowclone/sessions";
import { assessSkillBatch } from "./assess";
import { discoverSkills } from "@shadowclone/skills";
import { assessmentFingerprint } from "./prepare";
import { readMaintenanceState } from "@shadowclone/skills";
import { syncPortableSkills } from "@shadowclone/skills";
import { syncPersonalSkills } from "@shadowclone/skills";

export type SkillUpdateSummary = {
  readonly assessed: number;
  readonly applied: number;
  readonly pending: number;
  readonly invalid: number;
  readonly duplicates: number;
  readonly deferred: number;
  readonly verification: number;
  readonly synced: number;
  readonly conflicts: number;
  readonly held?: number;
  readonly libraryReviewed?: number;
  readonly libraryDeferred?: number;
};

export async function updateLegacySkillLibrary(options: {
  readonly paths: ProjectPaths;
  readonly execution?: LearningExecution;
  readonly syncPersonal?: boolean;
  readonly managedConfigPath?: string | null;
  readonly readRemote?: GitRemoteReader;
}): Promise<SkillUpdateSummary> {
  const empty: SkillUpdateSummary = {
    assessed: 0,
    applied: 0,
    pending: 0,
    invalid: 0,
    duplicates: 0,
    deferred: 0,
    verification: 0,
    synced: 0,
    conflicts: 0,
  };

  const { config, policy } = await readEffectiveConfig({
    configPath: options.paths.configFile,
    managedConfigPath:
      options.managedConfigPath === undefined
        ? options.paths.managedConfigFile
        : options.managedConfigPath,
  });

  if (!config.sources["skill-library"]) {
    return empty;
  }

  const lock = await acquireLocalLock(
    path.join(options.paths.shadowcloneDirectory, "skills-worker.db"),
  );

  if (!lock) {
    throw new Error("Another skill update is running");
  }

  try {
    const initialSync = options.syncPersonal
      ? await syncPersonalSkills({ paths: options.paths })
      : await syncPortableSkills({ paths: options.paths });

    if (
      !config.distillation.deep ||
      policy.distillation !== "allowed" ||
      !options.execution
    ) {
      return { ...empty, ...initialSync };
    }

    let state = await readMaintenanceState(options.paths);
    const profiles = new Map<string, string>();

    for (const root of state.roots) {
      if (!root.enabled) {
        continue;
      }

      const profile = await compileContext({
        ...options,
        cwd: root.cwd,
        scope: root.scope === "global" ? "global" : "combined",
      });

      if (profile !== null) {
        profiles.set(root.id, profile);
      }
    }

    const discovered = await discoverSkills(
      state.roots.filter((root) => profiles.has(root.id)),
    );

    const summary = {
      ...empty,
      invalid: discovered.invalid,
      duplicates: discovered.duplicates,
      ...initialSync,
    };

    let assessmentAvailable = true;

    for (const [rootId, profile] of profiles) {
      let pending = discovered.skills.filter(
        (skill) =>
          skill.root.id === rootId &&
          state.assessed[skill.id] !==
            assessmentFingerprint({ skill, profile }),
      );

      while (
        pending.length > 0 &&
        assessmentAvailable &&
        options.execution.callsRemaining() > 0
      ) {
        const batch = nextSkillBatch(pending);

        if (batch.length === 0) {
          break;
        }

        const result = await assessSkillBatch({
          skills: batch,
          profile,
          execution: options.execution,
          cwd: options.paths.shadowcloneDirectory,
        });

        if (result.status === "deferred") {
          assessmentAvailable = false;

          break;
        }

        state = await applyAssessedSkills({
          paths: options.paths,
          managedConfigPath: options.managedConfigPath,
          readRemote: options.readRemote,
          assessments: result.assessments,
          state,
          profile,
          duplicates: discovered.duplicates,
          summary,
        });

        pending = pending.slice(batch.length);
      }

      summary.deferred += pending.length;
    }

    const finalSync = await syncPortableSkills({ paths: options.paths });

    summary.synced += finalSync.synced;
    summary.conflicts += finalSync.conflicts;

    return summary;
  } finally {
    lock.release();
  }
}
