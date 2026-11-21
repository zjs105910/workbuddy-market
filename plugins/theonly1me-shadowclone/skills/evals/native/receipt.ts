import { z } from "zod";

export const verdictSchema = z.enum(["pass", "fail", "unknown"]);
export const checkSchema = z.strictObject({
  id: z.string(), verdict: verdictSchema, evidence: z.string().max(2000),
});
export const judgmentSchema = z.strictObject({
  checks: z.array(checkSchema),
  completion: verdictSchema,
  completionEvidence: z.string().max(2000),
});
export const changedFileSchema = z.strictObject({
  path: z.string(), before: z.string().nullable(), after: z.string().nullable(),
});
export const usageSchema = z.strictObject({ inputTokens: z.number(), cachedInputTokens: z.number(), outputTokens: z.number() });
export const voteSchema = z.strictObject({
  engine: z.enum(["claude-code", "codex"]), judgment: judgmentSchema.nullable(), error: z.string().nullable(),
  timedOut: z.boolean().default(false),
  resolvedModel: z.string().nullable(), cliVersion: z.string().nullable(),
  durationMs: z.number().nonnegative(), costUsd: z.number().nonnegative().nullable(),
  usage: usageSchema.nullable(), response: z.string(),
});

export type NativeVote = z.infer<typeof voteSchema>;
export type ChangedFile = z.infer<typeof changedFileSchema>;
