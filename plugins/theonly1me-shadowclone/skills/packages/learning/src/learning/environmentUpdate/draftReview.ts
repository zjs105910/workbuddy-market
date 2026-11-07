import type { SkillDraft } from "@shadowclone/environment";

export function pendingDraftReasons(draft: SkillDraft) {
  const blockingKeys = draft.outcomes
    .filter(({ disposition }) => disposition === "pending")
    .map(({ key }) => key);

  return draft.outcomes.map((outcome) => ({
    key: outcome.key,
    reason: outcome.disposition === "pending"
      ? outcome.reason
      : `The shared skill draft is blocked by learning ${blockingKeys.join(", ")}. Resolve those records and retry; no changes from this draft were applied.`,
  }));
}
