import { z } from "zod";
import { armEnvironmentSchema } from "../../native/study/schema";

export const learnerSchema = z.strictObject({ engine: z.enum(["codex", "claude-code"]), model: z.string().min(1),
  effort: z.enum(["medium", "high"]), cliVersion: z.string().min(1), maximumCalls: z.number().int().min(1).max(16),
  callSeconds: z.literal(120), deadlineSeconds: z.literal(1200) });
const startingSchema = z.strictObject({ original: armEnvironmentSchema, "first-time": armEnvironmentSchema });
const environmentsSchema = z.strictObject({ ...startingSchema.shape, deep: armEnvironmentSchema });

export const workflowPreparationSchema = z.strictObject({
  protocol: z.literal("preference-respect-v2"), version: z.literal(2), benchmarkFingerprint: z.string().length(64),
  product: z.strictObject({ commit: z.string(), tree: z.string().length(64), branch: z.string() }),
  runtime: z.strictObject({ bun: z.string(), typescript: z.string() }), graderFingerprint: z.string().length(64),
  corpusFingerprint: z.string().length(64), learningStateFingerprint: z.string().length(64), learner: learnerSchema,
  starting: z.strictObject({ codex: startingSchema, "claude-code": startingSchema }),
});

export const learningCallSchema = z.strictObject({ model: z.string(), cliVersion: z.string(), durationMs: z.number().nonnegative(), isError: z.boolean() });
export const preparedEnvironmentsSchema = z.strictObject({
  protocol: z.literal("preference-respect-v2"), preparation: workflowPreparationSchema,
  preparationFingerprint: z.string().length(64),
  learning: z.strictObject({ calls: z.array(learningCallSchema), outcome: z.enum(["complete", "incomplete"]),
    processedEpisodes: z.number().int().nonnegative(), pendingRules: z.number().int().nonnegative(),
    unresolvedSkills: z.number().int().nonnegative(), publishedRules: z.number().int().nonnegative() }),
  engines: z.strictObject({ codex: environmentsSchema, "claude-code": environmentsSchema }),
});

export type WorkflowPreparation = z.infer<typeof workflowPreparationSchema>;
export type PreparedEnvironments = z.infer<typeof preparedEnvironmentsSchema>;
export type LearnerConfiguration = z.infer<typeof learnerSchema>;
export type LearningCall = z.infer<typeof learningCallSchema>;
