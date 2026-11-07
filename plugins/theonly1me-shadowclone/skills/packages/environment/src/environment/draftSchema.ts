import { z } from "zod";
import type { LearningRecord } from "./types";

export const draftSchema = z.strictObject({
  description: z.string().max(1024),
  outcomes: z.array(z.strictObject({
    key: z.string(),
    disposition: z.enum(["apply", "covered", "pending", "retire"]),
    reason: z.string().trim().min(1).max(2000),
  })),
  edits: z.array(z.strictObject({
    before: z.string().max(48_000),
    after: z.string().max(48_000),
    keys: z.array(z.string()).min(1),
  })).max(16),
  body: z.string().max(48_000),
});

export type SkillDraft = z.infer<typeof draftSchema>;

export function retirementRequested(record: LearningRecord): boolean {
  return record.retirementRequested === true && record.rule.status === "stale" && record.rule.proposal === null;
}

export function validateDraftOutcomes(options: {
  readonly draft: SkillDraft;
  readonly records: readonly LearningRecord[];
}): void {
  const keys = new Set(options.draft.outcomes.map(({ key }) => key));

  if (
    keys.size !== options.records.length ||
    keys.size !== options.draft.outcomes.length ||
    options.records.some(({ rule }) => !keys.has(rule.key))
  ) {
    throw new Error("Skill draft did not account for every supplied learning");
  }
}

export function authorizeDraftOutcomes(options: {
  readonly draft: SkillDraft;
  readonly records: readonly LearningRecord[];
}): SkillDraft {
  validateDraftOutcomes(options);

  return {
    ...options.draft,
    outcomes: options.draft.outcomes.map((outcome) => {
      const record = options.records.find(({ rule }) => rule.key === outcome.key);

      return outcome.disposition === "retire" && record && !retirementRequested(record)
        ? {
            ...outcome,
            disposition: "pending" as const,
            reason: "No explicit retirement is recorded. Confirm retirement before removing this rule.",
          }
        : outcome;
    }),
  };
}
