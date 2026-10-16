import { explicitProfileEvidence } from "@shadowclone/profile";
import type { ReconciliationContext } from "./types";

export function unionEvidence(
  values: readonly string[],
  additions: readonly string[],
): readonly string[] {
  return [...new Set([...values, ...additions])];
}

export function materializeEvidenceIds(options: {
  readonly tokens: readonly string[];
  readonly context: ReconciliationContext;
  readonly explicitTokens: ReadonlySet<string>;
}): readonly string[] {
  const allowed = new Map(
    options.context.evidence.map((entry) => [entry.token, entry.evidenceId]),
  );

  return [
    ...new Set(
      options.tokens.flatMap((token) => {
        const evidenceId = allowed.get(token);

        return evidenceId
          ? [
              options.explicitTokens.has(token)
                ? explicitProfileEvidence(evidenceId)
                : evidenceId,
            ]
          : [];
      }),
    ),
  ];
}
