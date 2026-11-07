import { readEffectiveConfig } from "@shadowclone/core";
import type { LearningExecution } from "@shadowclone/agents";
import { readEnvironment, refreshIntegrations } from "@shadowclone/environment";
import { updateLearningEnvironment } from "./environmentUpdate/update";
import type { ProjectPaths } from "@shadowclone/core";
import type { GitRemoteReader } from "@shadowclone/sessions";
import { resolveLearningExecution } from "./execution";

export async function publishReviewedLearning(options: {
  readonly paths: ProjectPaths;
  readonly keys: readonly string[];
  readonly execution?: LearningExecution;
  readonly managedConfigPath?: string | null;
  readonly readRemote?: GitRemoteReader;
}): Promise<{ readonly applied: number; readonly pending: number }> {
  const { config, policy } = await readEffectiveConfig({
    configPath: options.paths.configFile,
    managedConfigPath: options.managedConfigPath === undefined
      ? options.paths.managedConfigFile : options.managedConfigPath,
  });
  const state = await readEnvironment(options.paths);
  let publication = { applied: 0, pending: 0 };

  if (options.keys.length === 0) return publication;

  for (const record of state?.records ?? []) {
    if (!options.keys.includes(record.rule.key) || record.retirementRequested) continue;
    const disabled = record.captureSources?.filter((source) => !config.sources[source]) ?? [];
    if (disabled.length > 0) {
      throw new Error(`Learned rule uses disabled sources: ${disabled.join(", ")}. Publication remains pending.`);
    }
  }

  if (state !== null && config.sources["skill-library"] &&
    config.distillation.deep && policy.distillation === "allowed") {
    const execution = options.execution ?? (await resolveLearningExecution({
      allowedEngines: policy.allowedEngines,
      engine: config.distillation.engine,
      model: config.distillation.model,
    })).execution;
    const summary = await updateLearningEnvironment({
      ...options,
      execution,
      learningKeys: options.keys,
    });
    publication = {
      applied: summary?.applied ?? 0,
      pending: (summary?.pending ?? 0) + (summary?.deferred ?? 0),
    };
  } else if (state !== null) {
    publication = { applied: 0, pending: options.keys.length };
  }

  await refreshIntegrations({
    paths: options.paths,
    configPath: options.paths.configFile,
    managedConfigPath: options.managedConfigPath,
    readRemote: options.readRemote,
  });

  return publication;
}
