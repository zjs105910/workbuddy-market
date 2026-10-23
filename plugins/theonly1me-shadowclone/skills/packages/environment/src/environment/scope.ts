import path from "node:path";
import type { ProjectPaths } from "@shadowclone/core";
import type {
  EnvironmentRepository,
  EnvironmentState,
  LearningRecord,
} from "./types";

export type LearningScope = {
  readonly key: string;
  readonly directory: string;
  readonly repository: EnvironmentRepository | null;
};

export function learningScopes(options: {
  readonly paths: ProjectPaths;
  readonly state: EnvironmentState;
}): readonly LearningScope[] {
  return [
    {
      key: "global",
      directory: path.dirname(options.paths.shadowcloneDirectory),
      repository: null,
    },
    ...options.state.repositories.map((repository) => ({
      key: `${repository.originDirectory}/${repository.repositoryName}`,
      directory: repository.directory,
      repository,
    })),
  ];
}

export function belongsToScope(options: {
  readonly record: LearningRecord;
  readonly scope: LearningScope;
}): boolean {
  const { rule } = options.record;

  if (options.scope.repository === null) {
    return rule.scope === "global";
  }

  return (
    rule.scope !== "global" &&
    rule.originDirectory === options.scope.repository.originDirectory &&
    (rule.scope === "org" ||
      rule.repositoryName === options.scope.repository.repositoryName)
  );
}

export function skillDirectories(scope: LearningScope): readonly string[] {
  return [
    ".agents/skills",
    ".claude/skills",
    ...(scope.repository === null ? [".gemini/config/skills"] : []),
  ].map((relative) => path.join(scope.directory, relative));
}
