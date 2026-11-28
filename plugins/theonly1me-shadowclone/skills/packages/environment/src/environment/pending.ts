import type { ProjectPaths } from "@shadowclone/core";
import { retirementRequested } from "./draftSchema";
import { recordFingerprint } from "./records";
import { belongsToScope, learningScopes } from "./scope";
import type { EnvironmentState } from "./types";

export function pendingLearningRecords(options: {
  readonly paths: ProjectPaths;
  readonly state: EnvironmentState;
}) {
  const scopes = learningScopes(options);

  return options.state.records.filter(({ rule }) => rule.source !== "imported").flatMap((record) => {
    const entry = { kind: "learning" as const, key: record.rule.key, title: record.rule.title, scope: record.rule.scope };

    if (retirementRequested(record) && !options.state.dispositions.some((disposition) =>
      disposition.key === record.rule.key && disposition.status === "published",
    )) return [];

    if (record.rule.status === "candidate") {
      return [{ ...entry, status: "candidate", reason: "Candidate needs stronger evidence of reusable guidance before publication." }];
    }

    if (record.rule.proposal !== null) {
      return [{ ...entry, status: "conflicting-evidence", reason: "Conflicting evidence needs review of the proposed change before publication." }];
    }

    if (record.rule.status === "stale" && !retirementRequested(record)) {
      return [{ ...entry, status: "retirement-review", reason: "Stale status does not authorize removal. Review the evidence and explicitly confirm any retirement." }];
    }

    const applicable = scopes.filter((scope) => belongsToScope({ record, scope }));

    if (applicable.length === 0) {
      return [{ ...entry, status: "unresolved-scope", reason: "No matching registered repository is available. Register a repository in this scope or keep the learning deferred." }];
    }

    return applicable.flatMap((scope) => {
      const disposition = options.state.dispositions.find((entry) =>
        entry.key === record.rule.key && entry.scope === scope.key &&
        entry.inputFingerprint === recordFingerprint(record),
      );

      return disposition && disposition.status !== "pending"
        ? []
        : [{
            ...entry,
            scope: scope.key,
            status: disposition ? "pending" : "awaiting-publication",
            reason: disposition?.reason ?? "Awaiting scoped publication. Run skills update to continue within the learning budget.",
          }];
    });
  });
}
