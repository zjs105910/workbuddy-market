import type { ProjectPaths } from "@shadowclone/core";
import { readRedactedEnvironment } from "./store";
import { recordFingerprint } from "./records";
import { belongsToScope, learningScopes } from "./scope";
import { publishedSkills } from "./catalog";

export async function environmentStatus(paths: ProjectPaths) {
  const state = await readRedactedEnvironment(paths);

  if (state === null) {
    return null;
  }

  const scopes = learningScopes({ paths, state });
  const applicable = state.records.filter(
    ({ rule }) => rule.status === "active" && rule.source !== "imported",
  );

  return {
    phase: state.phase,
    automatic: state.automatic,
    skills: publishedSkills({
      state,
      scopes: new Set(scopes.map(({ key }) => key)),
    }).length,
    pending: applicable.filter((record) =>
      scopes.some(
        (scope) =>
          belongsToScope({ record, scope }) &&
          !state.dispositions.some(
            (entry) =>
              entry.key === record.rule.key &&
              entry.scope === scope.key &&
              entry.status !== "pending" &&
              entry.inputFingerprint === recordFingerprint(record),
          ),
      ),
    ).length,
    unresolvedScopes: applicable.filter(
      (record) => !scopes.some((scope) => belongsToScope({ record, scope })),
    ).length,
  };
}
