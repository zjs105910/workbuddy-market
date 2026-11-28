import { z } from "zod";
import { changedFileSchema, usageSchema, voteSchema } from "../receipt";
import { checkResultSchema } from "./checkSchema";
import { workflowOutcomeSchema } from "../../shared/outcome";

export const runArmSchema = z.enum(["bare", "told", "original", "first-time", "deep"]);

export const actionSchema = z.strictObject({
  tool: z.string(),
  path: z.string().nullable(),
  command: z.string().nullable(),
  succeeded: z.boolean().nullable(),
  testRuns: z.array(z.enum(["pass", "fail"])).optional(),
});

export const commitSchema = z.strictObject({
  hash: z.string(),
  subject: z.string(),
  body: z.string(),
  trailers: z.string(),
});

export const toolCallSchema = z.strictObject({
  tool: z.string(),
  args: z.array(z.string()),
  body: z.string().nullable(),
});

export const turnRecordSchema = z.strictObject({
  index: z.number().int().min(0),
  response: z.string(),
  actions: z.array(actionSchema),
  skillReads: z.array(z.string()),
  changedPaths: z.array(z.string()),
  commits: z.array(commitSchema),
  branch: z.string().nullable(),
  resolvedModel: z.string().nullable(),
  durationMs: z.number().nonnegative(),
  costUsd: z.number().nonnegative().nullable(),
  usage: usageSchema.nullable(),
  isError: z.boolean(),
  timedOut: z.boolean(),
  error: z.string().nullable(),
});

export const runRecordSchema = z.strictObject({
  outcome: workflowOutcomeSchema.optional(),
  arm: runArmSchema,
  taskId: z.string(),
  repeat: z.number().int().min(0).max(4),
  productCommit: z.string().optional(),
  productTreeFingerprint: z.string().optional(),
  status: z.enum(["running", "complete", "error"]),
  turns: z.array(turnRecordSchema),
  files: z.array(changedFileSchema),
  commits: z.array(commitSchema),
  branch: z.string().nullable(),
  toolCalls: z.array(toolCallSchema),
  correctness: z.enum(["pass", "fail", "unknown"]),
  verificationEvidence: z.string(),
  safety: z.enum(["pass", "fail", "unknown"]),
  safetyEvidence: z.string(),
  checks: z.array(checkResultSchema),
  judgments: z.array(z.strictObject({ checkId: z.string(), votes: z.array(voteSchema) })),
  error: z.string().nullable(),
});

export type RunArmName = z.infer<typeof runArmSchema>;
export type StudyAction = z.infer<typeof actionSchema>;
export type StudyCommit = z.infer<typeof commitSchema>;
export type ToolCall = z.infer<typeof toolCallSchema>;
export type TurnRecord = z.infer<typeof turnRecordSchema>;
export type RunRecord = z.infer<typeof runRecordSchema>;

export function pendingRun(options: { arm: RunArmName; taskId: string; repeat: number }): RunRecord {
  return {
    ...options, status: "running", turns: [], files: [], commits: [], branch: null, toolCalls: [],
    correctness: "unknown", verificationEvidence: "Candidate has not completed.",
    safety: "unknown", safetyEvidence: "Candidate has not completed.", checks: [], judgments: [], error: null,
  };
}
