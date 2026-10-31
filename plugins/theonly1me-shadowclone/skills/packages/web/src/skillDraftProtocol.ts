import { z } from "zod";
import { customSkillSchema } from "@shadowclone/environment/browser";

export const skillBriefSchema = z.strictObject({
  name: z.string().trim().max(48),
  description: z.string().trim().max(300),
  body: z.string().trim().min(1).max(24_000),
});

export const skillDraftReviewSchema = z.strictObject({
  id: z.uuid(),
  destination: z.string(),
  payload: z.string(),
  limits: z.string(),
  cached: customSkillSchema.nullable(),
});

export const skillDraftResultSchema = z.strictObject({
  skill: customSkillSchema,
});
