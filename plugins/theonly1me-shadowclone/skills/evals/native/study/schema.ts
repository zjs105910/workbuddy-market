import { z } from "zod";
import { commandSchema, fileSchema, nativeFileSchema } from "../schema";
import { checkSchema } from "./checkSchema";

export const studyArms = ["bare", "original", "first-time", "deep"] as const;
export const controlArms = ["bare", "told"] as const;
export const studyEngines = {
  codex: { model: "gpt-6-sol", effort: "medium" },
  "claude-code": { model: "claude-sonnet-5-5", effort: "high" },
} as const;
export const personalArms = ["original", "first-time", "deep"] as const;
export const keyGroups = ["personal", "wizard", "learned", "resolved"] as const;

export type StudyArm = (typeof studyArms)[number];
export type ControlArm = (typeof controlArms)[number];
export type PersonalArm = (typeof personalArms)[number];
export type KeyGroup = (typeof keyGroups)[number];

const identifierSchema = z.string().regex(/^[a-z][a-z0-9-]*$/);
const branchSchema = z.string().regex(/^[a-z0-9][a-z0-9._/-]{0,99}$/);

export const keyItemSchema = z.strictObject({
  id: identifierSchema,
  group: z.enum(keyGroups),
  statement: z.string().min(10).max(600),
  evidence: z.string().min(1).max(400),
});

export const gitSchema = z.strictObject({
  branches: z.array(z.strictObject({
    name: branchSchema,
    from: branchSchema.optional(),
    commits: z.array(z.strictObject({
      message: z.string().min(1).max(2000),
      files: z.array(fileSchema).min(1),
    })).min(1),
  })).min(1),
  checkout: branchSchema,
  pushed: z.boolean(),
});

export const taskSchema = z.strictObject({
  id: identifierSchema,
  mode: z.enum(["code", "advice"]),
  turns: z.array(z.string().min(1).max(16000)).min(1).max(4),
  git: gitSchema.nullable(),
  fixtures: z.array(fileSchema),
  acceptance: z.strictObject({
    files: z.array(fileSchema),
    commands: z.array(commandSchema).min(1),
    reference: z.array(fileSchema).min(1),
  }).nullable(),
  checks: z.array(checkSchema).min(1).max(8),
});

export const armEnvironmentSchema = z.strictObject({
  files: z.array(nativeFileSchema),
  fingerprint: z.string().length(64),
});

export const droppedCheckSchema = z.strictObject({
  taskId: identifierSchema,
  checkId: identifierSchema,
  reason: z.enum(["default-behavior", "told-failed", "not-applicable", "calibration-failed"]),
});

export const studySuiteSchema = z.strictObject({
  protocol: z.literal("preference-study-v1"),
  version: z.literal(1),
  studyId: z.uuid(),
  productCommit: z.string().regex(/^[a-f0-9]{40}$/),
  productTreeFingerprint: z.string().length(64),
  templateDirectory: z.string().min(1),
  templateFingerprint: z.string().length(64),
  cliVersion: z.string().min(1),
  engine: z.enum(["codex", "claude-code"]).default("codex"),
  model: z.string().min(1),
  effort: z.enum(["medium", "high"]),
  keyItems: z.array(keyItemSchema).min(4).max(40),
  wizardBuild: z.array(identifierSchema).min(1),
  resolutionRule: z.string().min(20).max(1000),
  arms: z.strictObject({
    original: armEnvironmentSchema,
    "first-time": armEnvironmentSchema,
    deep: armEnvironmentSchema,
  }),
  memory: z.array(fileSchema),
  tasks: z.array(taskSchema).min(1).max(12),
  droppedChecks: z.array(droppedCheckSchema),
  analysis: z.strictObject({
    repetitions: z.number().int().min(1).max(5),
    bootstrapSeed: z.number().int().nonnegative(),
    bootstrapSamples: z.number().int().min(1000).max(100000),
  }),
  limits: z.strictObject({
    maximumCalls: z.number().int().min(1).max(1000),
    concurrency: z.number().int().min(1).max(16),
    codeTurnSeconds: z.number().int().min(30).max(900),
    adviceTurnSeconds: z.number().int().min(30).max(900),
    judgeSeconds: z.number().int().min(15).max(300),
  }),
});

export type KeyItem = z.infer<typeof keyItemSchema>;
export type StudyTask = z.infer<typeof taskSchema>;
export type StudySuite = z.infer<typeof studySuiteSchema>;
export type GitHistory = z.infer<typeof gitSchema>;
export type ArmEnvironment = z.infer<typeof armEnvironmentSchema>;
export type DroppedCheck = z.infer<typeof droppedCheckSchema>;
