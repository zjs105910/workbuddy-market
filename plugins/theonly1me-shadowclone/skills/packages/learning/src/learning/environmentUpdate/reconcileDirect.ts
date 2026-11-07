import type { ProjectPaths } from "@shadowclone/core";
import type { LearningRoute } from "./planner";
import {
  type EnvironmentState,
  type LearningRecord,
  type LearningScope,
  recordFingerprint,
  validateRouting,
} from "@shadowclone/environment";

export function reconcileDirectLearning(options: {
  readonly paths: ProjectPaths;
  readonly state: EnvironmentState;
  readonly scope: LearningScope;
  readonly route: LearningRoute;
  readonly records: readonly LearningRecord[];
  readonly keys: ReadonlySet<string>;
}): EnvironmentState {
  const { route, records, keys } = options;
  let state = options.state;

  const facts = records.map((record) => ({
    scope: options.scope.key,
    text: record.rule.body,
    learningKeys: [record.rule.key],
  }));
  const previousFacts = state.facts;

  state = {
    ...state,
    facts:
      route.destination === "fact"
        ? [
            ...state.facts.filter(
              (fact) => !fact.learningKeys.some((key) => keys.has(key)),
            ),
            ...facts,
          ]
        : state.facts,
    dispositions: [
      ...state.dispositions.filter(
        (entry) => !keys.has(entry.key) || entry.scope !== options.scope.key,
      ),
      ...records.map((record) => ({
        key: record.rule.key,
        scope: options.scope.key,
        inputFingerprint: recordFingerprint(record),
        publishedAt: route.destination === "fact" ? Date.now() : undefined,
        status:
          route.destination === "excluded"
            ? ("excluded" as const)
            : route.destination === "fact"
              ? ("published" as const)
              : ("pending" as const),
        reason: `${record.rule.title}: ${route.reason}`,
        destinations: route.destination === "fact" ? ["native-context"] : [],
      })),
    ],
  };

  if (route.destination === "fact") {
    try {
      validateRouting({ paths: options.paths, state });
    } catch {
      state = {
        ...state,
        facts: previousFacts,
        dispositions: state.dispositions.map((entry) =>
          keys.has(entry.key) && entry.scope === options.scope.key
            ? {
                ...entry,
                status: "pending",
                reason:
                  "Native context exceeds its 4 KiB budget; move this knowledge into a workflow skill",
                destinations: [],
              }
            : entry,
        ),
      };
    }
  }

  return state;
}
