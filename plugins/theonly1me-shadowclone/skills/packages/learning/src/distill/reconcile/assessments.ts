import type { ReconciliationContext, ReconciliationOutput } from "./types";

export function assessedContext(options: {
  readonly context: ReconciliationContext;
  readonly output: ReconciliationOutput;
}): ReconciliationContext {
  return {
    ...options.context,
    evidence: options.context.evidence.filter((entry) => {
      if (entry.signal.kind !== "user-steering") {
        return true;
      }

      const assessments = (options.output.assessments ?? []).filter(
        (assessment) => assessment.evidenceToken === entry.token,
      );
      const [assessment] = assessments;

      return (
        assessments.length === 1 &&
        assessment?.durable === true &&
        (assessment.intent === "preference" ||
          assessment.intent === "correction" ||
          assessment.intent === "approval")
      );
    }),
  };
}

export function explicitEvidenceTokens(
  output: ReconciliationOutput,
): ReadonlySet<string> {
  return new Set(
    (output.assessments ?? [])
      .filter((assessment) => assessment.explicit === true)
      .map((assessment) => assessment.evidenceToken),
  );
}

export function globalEvidenceTokens(
  output: ReconciliationOutput,
): ReadonlySet<string> {
  return new Set(
    (output.assessments ?? [])
      .filter(
        (assessment) =>
          assessment.explicit === true && assessment.scope === "global",
      )
      .map((assessment) => assessment.evidenceToken),
  );
}
