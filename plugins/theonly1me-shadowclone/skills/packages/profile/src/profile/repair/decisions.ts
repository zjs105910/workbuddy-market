import { z } from "zod";

const locationSchema = z.discriminatedUnion("scope", [
  z.strictObject({ scope: z.literal("global") }),
  z.strictObject({
    scope: z.literal("org"),
    originDirectory: z.string().min(1),
  }),
  z.strictObject({
    scope: z.literal("project"),
    originDirectory: z.string().min(1),
    repositoryName: z.string().min(1),
  }),
]);

const rejectionReasonSchema = z.enum([
  "skill-covered",
  "repo-covered",
  "stale",
  "synthetic",
  "one-off",
  "duplicate",
  "user-rejected",
]);

const sectionSchema = z.enum(["engineering", "workflow", "boundaries"]);

const ruleDecisionSchema = z.discriminatedUnion("action", [
  z.strictObject({
    action: z.literal("move"),
    key: z.string().min(1),
    section: sectionSchema,
    location: locationSchema,
  }),
  z.strictObject({
    action: z.literal("reject"),
    key: z.string().min(1),
    reason: rejectionReasonSchema,
  }),
  z.strictObject({
    action: z.literal("reference"),
    key: z.string().min(1),
    reason: rejectionReasonSchema,
    reference: z.strictObject({
      key: z.string().regex(/^[a-z0-9][a-z0-9._-]*$/),
      title: z.string().min(1).max(200),
      summary: z.string().min(1).max(1_000),
      tags: z.array(z.string().min(1).max(80)).max(32),
      updatedAt: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
      location: locationSchema,
    }),
  }),
]);

const decisionsSchema = z.strictObject({
  rules: z.array(ruleDecisionSchema).min(1),
});

export type ProfileCurationDecision = z.infer<typeof ruleDecisionSchema>;

export type ProfileCurationDecisions = {
  readonly rules: readonly ProfileCurationDecision[];
};

export function parseProfileCurationDecisions(
  text: string,
): ProfileCurationDecisions {
  let value: unknown;

  try {
    value = JSON.parse(text);
  } catch {
    throw new Error("Profile repair decisions must be valid JSON");
  }

  const parsed = decisionsSchema.safeParse(value);

  if (!parsed.success) {
    throw new Error("Profile repair decisions are invalid");
  }

  const keys = parsed.data.rules.map((decision) => decision.key);

  if (new Set(keys).size !== keys.length) {
    throw new Error("Profile repair decisions contain duplicate rule keys");
  }

  return parsed.data;
}
