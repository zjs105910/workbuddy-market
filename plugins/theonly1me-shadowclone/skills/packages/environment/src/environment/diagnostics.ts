import { readEffectiveConfig } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";
import {
  resolveRepository,
  isOriginBlocked,
  type GitRemoteReader,
} from "@shadowclone/sessions";
import { readRedactedEnvironment } from "./store";
import { belongsToScope, learningScopes } from "./scope";
import { publishedSkills } from "./catalog";
import { recordFingerprint } from "./records";

export async function explainLearningEnvironment(options: {
  readonly paths: ProjectPaths;
  readonly cwd: string;
  readonly readRemote?: GitRemoteReader;
}): Promise<string | null> {
  const state = await readRedactedEnvironment(options.paths);

  if (state?.phase !== "active") {
    return null;
  }

  const { config, policy } = await readEffectiveConfig({
    configPath: options.paths.configFile,
    managedConfigPath: options.paths.managedConfigFile,
  });

  if (!policy.enabled) {
    return "Skill delivery is disabled by policy.";
  }

  const repository = await resolveRepository({
    cwd: options.cwd,
    enabled: config.sources["git-metadata"],
    readRemote: options.readRemote,
  });

  if (isOriginBlocked({ repository, patterns: policy.blockedOrigins })) {
    return "Skill delivery is disabled for this repository.";
  }

  const scopes = learningScopes({ paths: options.paths, state }).filter(
    (scope) =>
      scope.repository === null ||
      (scope.repository.originDirectory === repository.origin.directoryName &&
        scope.repository.repositoryName === repository.profileFileName),
  );

  const keys = new Set(scopes.map(({ key }) => key));
  const records = state.records.filter((record) =>
    scopes.some((scope) => belongsToScope({ record, scope })),
  );

  return JSON.stringify(
    {
      delivery: "skills",
      automatic: state.automatic,
      skills: publishedSkills({ state, scopes: keys }).map((artifact) => ({
        name: artifact.name,
        description: artifact.description,
        path: artifact.filePath,
        learnings: artifact.learningKeys,
      })),
      facts: state.facts.filter((fact) => keys.has(fact.scope)),
      learnings: records.map((record) => ({
        key: record.rule.key,
        title: record.rule.title,
        scope: record.rule.scope,
        evidence: record.rule.evidence,
        source: record.sourceLocator,
        disposition: state.dispositions.find(
          (entry) => entry.key === record.rule.key &&
            keys.has(entry.scope ?? "") && entry.inputFingerprint === recordFingerprint(record),
        ) ?? { status: "pending" },
      })),
    },
    null,
    2,
  );
}
