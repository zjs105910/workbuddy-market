import {
  profileEvidenceStatistics,
  isExplicitProfileEvidence,
  type ProfileEvidence,
  type ProfileRule,
} from "@shadowclone/profile";
import type { ReconciliationChange } from "./reconcile";

function union(
  left: readonly string[],
  right: readonly string[],
): readonly string[] {
  return [...new Set([...left, ...right])];
}

export function mergeProfileRuleUpdates(
  rules: readonly ProfileRule[],
): readonly ProfileRule[] {
  const merged = new Map<string, ProfileRule>();

  for (const rule of rules) {
    const previous = merged.get(rule.key);

    if (!previous) {
      merged.set(rule.key, rule);

      continue;
    }

    const evidence: ProfileEvidence = {
      for: union(previous.evidence.for, rule.evidence.for),
      against: union(previous.evidence.against, rule.evidence.against),
    };
    const combined = {
      ...previous,
      evidence,
      proposal: rule.proposal ?? previous.proposal,
    };
    const statistics = profileEvidenceStatistics({ rule: combined, evidence });

    const status =
      combined.source !== "mined"
        ? ("active" as const)
        : evidence.against.length > 0
          ? ("stale" as const)
          : evidence.for.some(isExplicitProfileEvidence) ||
              statistics.sessions >= 3
            ? ("active" as const)
            : ("candidate" as const);

    merged.set(rule.key, { ...combined, ...statistics, status });
  }

  return [...merged.values()];
}

export function finalizeReconciliationChanges(options: {
  readonly changes: readonly ReconciliationChange[];
  readonly existingRules: readonly ProfileRule[];
  readonly newRules: readonly ProfileRule[];
}): readonly ReconciliationChange[] {
  const finalByKey = new Map(
    [...options.existingRules, ...options.newRules].map((rule) => [
      rule.key,
      rule,
    ]),
  );

  const existing = new Map<string, ReconciliationChange>();

  for (const change of options.changes.filter(
    (entry) => entry.kind !== "new",
  )) {
    const after = finalByKey.get(change.after.key);

    if (after) {
      existing.set(change.after.key, { ...change, after });
    }
  }

  const observations = new Map(
    options.changes
      .filter((entry) => entry.kind === "new")
      .map((entry) => [entry.after.key, entry.observed]),
  );

  const added = options.newRules.map((after) => ({
    kind: "new" as const,
    observed:
      observations.get(after.key) ?? "Combined related correction evidence.",
    before: null,
    after,
  }));

  return [...existing.values(), ...added];
}
