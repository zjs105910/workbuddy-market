import { z } from "zod";
import type { ClaudeFeedbackDecision } from "./types";

const decisionSchema = z.discriminatedUnion("disposition", [
  z.strictObject({
    disposition: z.literal("rule"),
    title: z.string().min(1).max(200),
    scope: z.enum(["global", "project"]),
    section: z.enum(["engineering", "workflow", "boundaries"]),
  }),
  z.strictObject({
    disposition: z.literal("rejected"),
    reason: z.enum([
      "skill-covered",
      "repo-covered",
      "stale",
      "synthetic",
      "one-off",
      "duplicate",
      "user-rejected",
    ]),
  }),
]);

const decisionsSchema = z.strictObject({
  feedback: z.record(z.string().min(1), decisionSchema),
  excludeReferences: z.array(z.string().min(1)).default([]),
});

export type ClaudeMemoryDecisions = {
  readonly feedback: ReadonlyMap<string, ClaudeFeedbackDecision>;
  readonly excludeReferences: ReadonlySet<string>;
};

export function parseClaudeMemoryDecisions(
  text: string,
): ClaudeMemoryDecisions {
  let value: unknown;

  try {
    value = JSON.parse(text);
  } catch {
    throw new Error("Claude memory decisions must be valid JSON");
  }

  const parsed = decisionsSchema.safeParse(value);

  if (!parsed.success) {
    throw new Error("Claude memory decisions are invalid");
  }

  return {
    feedback: new Map(Object.entries(parsed.data.feedback)),
    excludeReferences: new Set(parsed.data.excludeReferences),
  };
}
