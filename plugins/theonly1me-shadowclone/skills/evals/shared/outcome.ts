import { z } from "zod";

export const workflowOutcomeSchema = z.strictObject({
  accepted: z.boolean(),
  humanReviewMinutes: z.number().nonnegative(),
  repeatedCorrections: z.number().int().nonnegative(),
  regressions: z.number().int().nonnegative(),
  interventions: z.number().int().nonnegative(),
  costUsd: z.number().nonnegative().nullable(),
  reportedBy: z.literal("user"),
});

export type WorkflowOutcome = z.infer<typeof workflowOutcomeSchema>;

export function summarizeOutcomes(outcomes: readonly WorkflowOutcome[]) {
  const total = (select: (outcome: WorkflowOutcome) => number) =>
    outcomes.reduce((sum, outcome) => sum + select(outcome), 0);
  const knownCosts = outcomes.filter((outcome) => outcome.costUsd !== null);
  return {
    reported: outcomes.length,
    accepted: outcomes.filter((outcome) => outcome.accepted).length,
    humanReviewMinutes: total((outcome) => outcome.humanReviewMinutes),
    repeatedCorrections: total((outcome) => outcome.repeatedCorrections),
    regressions: total((outcome) => outcome.regressions),
    interventions: total((outcome) => outcome.interventions),
    knownCostUsd:
      knownCosts.length === 0 ? null : total((outcome) => outcome.costUsd ?? 0),
    unknownCostRuns: outcomes.length - knownCosts.length,
    provenance:
      "User-reported outcomes; missing reports and costs are not zero",
  };
}
