import { migrationRepositories } from "./migrationRepositories";
import { renderProfileRejections, readLegacyProfileSnapshot } from "@shadowclone/profile";
import { readEffectiveConfig, acquireLocalLock, readLocalText } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";
import type { GitRemoteReader } from "@shadowclone/sessions";
import { configureSkillMaintenance } from "@shadowclone/skills";
import { readEnvironment, environmentFile, renderEnvironment } from "./store";
import {
  emptyEnvironment,
  learningRuleSchema,
  type EnvironmentState,
  type LearningRecord,
} from "./types";
import { freezeOriginalEnvironment } from "./freeze";
import path from "node:path";
import { publishEnvironmentRevision } from "./revision";
import { ensureBaselineSkill } from "./initialize";
import { legacyManualLearning } from "./legacy";

export async function prepareEnvironmentMigration(options: {
  readonly paths: ProjectPaths;
  readonly repositories: readonly string[];
  readonly automatic: boolean;
  readonly apply: boolean;
  readonly readRemote?: GitRemoteReader;
  readonly managedConfigPath?: string | null;
}): Promise<EnvironmentState> {
  const { config, policy } = await readEffectiveConfig({
    configPath: options.paths.configFile,
    managedConfigPath:
      options.managedConfigPath === undefined
        ? options.paths.managedConfigFile
        : options.managedConfigPath,
  });

  if (!policy.enabled) {
    throw new Error("Managed policy blocks environment migration");
  }

  const lock = options.apply
    ? await acquireLocalLock(
        path.join(options.paths.shadowcloneDirectory, "environment-write.db"),
      )
    : null;

  if (options.apply && !lock) {
    throw new Error("Another learning update is running");
  }

  try {
    const previous = await readEnvironment(options.paths);
    const state: EnvironmentState = previous ?? { ...emptyEnvironment };
    const legacy =
      previous === null ? await readLegacyProfileSnapshot(options.paths) : null;

    const records = new Map<string, LearningRecord>(
      (legacy?.rules ?? []).map(
        ({
          rule,
          promptBody,
          promptTitle,
          promptAppliesWhen,
          promptProposal,
        }) => [
          rule.key,
          {
            kind: "guidance",
            sourceHash: null,
            sourceLocator: null,
            rule: learningRuleSchema.parse({
              ...rule,
              body: promptBody,
              title: promptTitle,
              appliesWhen: promptAppliesWhen,
              proposal: promptProposal,
            }),
          },
        ],
      ),
    );

    for (const record of state.records) {
      records.set(record.rule.key, record);
    }

    if (previous === null) {
      for (const record of await legacyManualLearning(options.paths)) {
        records.set(record.rule.key, record);
      }
    }

    const repositories = await migrationRepositories({
      ...options,
      state,
      records,
      repositoryConsent: config.sources["git-metadata"],
      blockedOrigins: policy.blockedOrigins,
    });

    const migrated = {
      ...state,
      automatic: options.automatic || state.automatic,
      records: [...records.values()],
      repositories,
      rejected: [
        ...new Set([
          ...state.rejected,
          ...(legacy?.rejections ?? []).map(({ rejection }) => rejection.key),
        ]),
      ],
      rejectionText:
        state.rejectionText ||
        renderProfileRejections(
          (legacy?.rejections ?? []).map(
            ({ rejection, promptTitle, promptBody }) => ({
              ...rejection,
              title: promptTitle,
              body: promptBody,
            }),
          ),
        ),
    };

    if (!options.apply) {
      return migrated;
    }

    for (const repository of repositories) {
      await configureSkillMaintenance({
        scope: "repository",
        paths: options.paths,
        cwd: repository.directory,
        managedConfigPath: options.managedConfigPath,
      });
    }

    const baselineDirectory =
      state.baselineDirectory ??
      (await freezeOriginalEnvironment(options.paths));
    const filePath = environmentFile(options.paths);

    await publishEnvironmentRevision({
      paths: options.paths,
      updates: [
        {
          filePath,
          previous: await readLocalText(filePath),
          next: renderEnvironment({ ...migrated, baselineDirectory }),
        },
      ],
    });
    await ensureBaselineSkill(options.paths);

    return (
      (await readEnvironment(options.paths)) ?? {
        ...migrated,
        baselineDirectory,
      }
    );
  } finally {
    lock?.release();
  }
}
