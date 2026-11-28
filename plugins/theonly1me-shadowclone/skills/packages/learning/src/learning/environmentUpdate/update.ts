import { updateLearningScope } from "./updateScope";
import path from "node:path";
import { readEffectiveConfig, readLocalText, acquireLocalLock } from "@shadowclone/core";
import type { LearningExecution } from "@shadowclone/agents";
import type { ProjectPaths } from "@shadowclone/core";
import { readMaintenanceState, syncPersonalSkills, syncPortableSkills } from "@shadowclone/skills";
import type { SkillUpdateSummary } from "../skillMaintenance/legacyUpdate";
import { isOriginBlocked, resolveRepository, type GitRemoteReader } from "@shadowclone/sessions";
import {
  environmentFile,
  learningScopes,
  publishEnvironmentRevision,
  readEnvironment,
  recordFingerprint,
  renderEnvironment,
  syncLearningEnvironment,
} from "@shadowclone/environment";
import { extractMemoryRecords } from "./memory";
import { reviewSkillConflicts } from "../skillMaintenance/conflicts";

export async function updateLearningEnvironment(options: {
  readonly paths: ProjectPaths;
  readonly execution?: LearningExecution;
  readonly syncPersonal?: boolean;
  readonly managedConfigPath?: string | null;
  readonly readRemote?: GitRemoteReader;
  readonly learningKeys?: readonly string[];
}): Promise<SkillUpdateSummary | null> {
  const initial = await readEnvironment(options.paths);

  if (initial === null) {
    return null;
  }

  const summary = {
    assessed: 0,
    applied: 0,
    pending: 0,
    invalid: 0,
    duplicates: 0,
    deferred: 0,
    verification: 0,
    held: 0,
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

  if (!config.sources["skill-library"] || !policy.enabled) {
    return summary;
  }

  if (!initial.automatic && options.learningKeys === undefined) {
    return {
      ...summary,
      pending: initial.records.filter(
        ({ rule }) => rule.status === "active" && rule.source !== "imported",
      ).length,
    };
  }

  const synchronized = options.learningKeys !== undefined
    ? { synced: 0, conflicts: 0 }
    : options.syncPersonal
    ? await syncPersonalSkills({ paths: options.paths })
    : await syncPortableSkills({ paths: options.paths });

  summary.synced = synchronized.synced;
  summary.conflicts = synchronized.conflicts;

  if (initial.phase === "active" && options.learningKeys === undefined) {
    await syncLearningEnvironment(options.paths);
  }

  if (
    policy.distillation !== "allowed" ||
    !config.distillation.deep ||
    !options.execution
  ) {
    return summary;
  }

  const lock = await acquireLocalLock(
    path.join(options.paths.shadowcloneDirectory, "environment-write.db"),
  );

  if (!lock) {
    throw new Error("Another learning environment update is running");
  }

  try {
    const stored = await readEnvironment(options.paths);

    if (stored === null) {
      throw new Error("Learning environment disappeared");
    }

    let state = stored;

    if (!state.automatic && options.learningKeys === undefined) {
      return { ...summary, pending: state.records.length };
    }

    const registered = [];

    for (const repository of state.repositories) {
      const resolved = await resolveRepository({
        cwd: repository.directory,
        enabled: config.sources["git-metadata"],
        readRemote: options.readRemote,
      });

      if (
        !isOriginBlocked({
          repository: resolved,
          patterns: policy.blockedOrigins,
        }) &&
        resolved.origin.directoryName === repository.originDirectory &&
        resolved.profileFileName === repository.repositoryName
      ) {
        registered.push(repository);
      }
    }

    const extracted = options.learningKeys !== undefined ? state : await extractMemoryRecords({
      paths: options.paths,
      state: { ...state, repositories: registered },
      enabled: config.sources["claude-memory"],
    });

    state = { ...extracted, repositories: state.repositories };

    const filePath = environmentFile(options.paths);

    await publishEnvironmentRevision({
      paths: options.paths,
      updates: [
        {
          filePath,
          previous: await readLocalText(filePath),
          next: renderEnvironment(state),
        },
      ],
    });

    const maintenance = await readMaintenanceState(options.paths);

    for (const scope of learningScopes({
      paths: options.paths,
      state: { ...state, repositories: registered },
    })) {
      state = await updateLearningScope({
        paths: options.paths,
        execution: options.execution,
        readRemote: options.readRemote,
        state,
        scope,
        maintenance,
        filePath,
        summary,
        learningKeys: options.learningKeys,
      });
    }

    summary.pending = state.dispositions.filter(
      ({ status, key }) => status === "pending" &&
        (options.learningKeys === undefined || options.learningKeys.includes(key)),
    ).length;
    summary.deferred = state.records.filter(
      (record) =>
        record.rule.status === "active" &&
        record.rule.source !== "imported" &&
        (options.learningKeys === undefined || options.learningKeys.includes(record.rule.key)) &&
        !state.dispositions.some(
          (entry) =>
            entry.key === record.rule.key &&
            entry.inputFingerprint === recordFingerprint(record),
        ),
    ).length;

    const review = options.learningKeys !== undefined
      ? { pending: 0, reviewed: 0, deferred: 0 }
      : await reviewSkillConflicts({
      paths: options.paths,
      execution: options.execution,
      repositoryDirectories: registered.map(({ directory }) => directory),
    });

    return {
      ...summary,
      pending: summary.pending + review.pending,
      conflicts: summary.conflicts + review.pending,
      libraryReviewed: review.reviewed,
      libraryDeferred: review.deferred,
    };
  } finally {
    lock.release();
  }
}
