import { recordFingerprint } from "./records";
import type { LearningScope } from "./scope";
import type { EnvironmentState, LearningRecord } from "./types";

export function pendingLearningState(options: {
  readonly state: EnvironmentState;
  readonly records: readonly LearningRecord[];
  readonly keys: ReadonlySet<string>;
  readonly scope: LearningScope;
  readonly reasons: readonly { readonly key: string; readonly reason: string }[];
  readonly destinations: string[];
}): EnvironmentState {
  const { state, records, keys } = options;
  const reasons = new Map(options.reasons.map(({ key, reason }) => [key, reason]));

  if (records.some(({ rule }) => !reasons.get(rule.key)?.trim())) {
    throw new Error("Pending learning needs a reason for every record");
  }

  return {
    ...state,
    dispositions: [
      ...state.dispositions.filter(
        (entry) => !keys.has(entry.key) || entry.scope !== options.scope.key,
      ),
      ...records.map((record) => ({
        key: record.rule.key,
        scope: options.scope.key,
        inputFingerprint: recordFingerprint(record),
        status: "pending" as const,
        reason: `${record.rule.title}: ${reasons.get(record.rule.key)}`,
        destinations: [...options.destinations],
      })),
    ],
  };
}

export function coveredLearningState(options: {
  readonly state: EnvironmentState;
  readonly records: readonly LearningRecord[];
  readonly keys: ReadonlySet<string>;
  readonly scope: LearningScope;
  readonly target: string;
  readonly fingerprint: string;
}): EnvironmentState {
  const { state, records, keys } = options;

  return {
    ...state,
    dispositions: [
      ...state.dispositions.filter(
        (entry) => !keys.has(entry.key) || entry.scope !== options.scope.key,
      ),
      ...records.map((record) => ({
        key: record.rule.key,
        scope: options.scope.key,
        inputFingerprint: recordFingerprint(record),
        status: "covered" as const,
        publishedAt: Date.now(),
        reason:
          "The complete learning is already present in the existing skill",
        destinations: [options.target],
        fingerprints: { [options.target]: options.fingerprint },
      })),
    ],
  };
}
