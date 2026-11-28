import type { ReconciliationContext, ReconciliationOutput } from "./reconcile/types";

export type AssessedCorrection = {
  readonly key: string;
  readonly evidenceId: string;
  readonly timestamp: number;
  readonly sessionId: string;
};

export function assessedCorrections(options: {
  readonly context: ReconciliationContext;
  readonly output: ReconciliationOutput;
}): readonly AssessedCorrection[] {
  const tokens = new Set(options.output.assessments?.filter((assessment) =>
    assessment.intent === "correction" && assessment.durable,
  ).map((assessment) => assessment.evidenceToken));

  return options.output.existingRules.flatMap((match) => {
    const rule = options.context.rules.find((entry) => entry.token === match.ruleToken);
    if (!rule) return [];
    return options.context.evidence.filter((evidence) =>
      tokens.has(evidence.token) && match.evidenceTokens.includes(evidence.token),
    ).map((evidence) => ({
      key: rule.snapshot.rule.key,
      evidenceId: evidence.evidenceId,
      timestamp: evidence.signal.timestamp,
      sessionId: evidence.signal.sessionId,
    }));
  });
}
