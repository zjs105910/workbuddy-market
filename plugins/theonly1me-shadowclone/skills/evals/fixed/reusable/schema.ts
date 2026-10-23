import { z } from "zod";
import { armEnvironmentSchema, taskSchema } from "../../native/study/schema";
import { checkResultSchema, checkSchema, patternSchema } from "../../native/study/checkSchema";
import { runRecordSchema } from "../../native/study/record";
import { learnerSchema, learningCallSchema } from "../workflow/schema";

export const families = [
  "comments",
  "types",
  "api",
  "git",
  "length",
  "test-first",
  "pr",
  "scope",
] as const;
export const setups = ["bare", "skills", "routing", "told", "deep"] as const;
export const digestSchema = z.string().regex(/^[a-f0-9]{64}$/);
export const extraCheckSchema = z.discriminatedUnion("kind", [
  z.strictObject({
    id: z.string(),
    kind: z.literal("word-range"),
    turn: z.number().int().nonnegative(),
    minimum: z.number().int().positive(),
    maximum: z.number().int().positive(),
  }),
  z.strictObject({
    id: z.string(),
    kind: z.literal("required-file"),
    path: z.string(),
    pattern: patternSchema,
  }),
  z.strictObject({ id: z.string(), kind: z.literal("result-api"), path: z.string() }),
  z.strictObject({ id: z.string(), kind: z.literal("no-remote-action") }),
  z.strictObject({
    id: z.string(),
    kind: z.literal("no-test-edit"),
    turn: z.number().int().nonnegative(),
  }),
]);
export const caseSchema = z.strictObject({
  family: z.enum(families),
  split: z.enum(["development", "held-out"]),
  repository: z.enum(["atlas", "boreal"]),
  task: taskSchema,
  extraChecks: z.array(extraCheckSchema),
  correctnessChecks: z.array(checkSchema).default([]),
  specification: z.string().min(20),
});
export const bundleSchema = z.strictObject({
  protocol: z.literal("preference-respect-v3"),
  cases: z.array(caseSchema).length(8),
});
export const publishedBundleSchema = z.strictObject({
  protocol: z.literal("preference-respect-v3"),
  fingerprint: digestSchema,
  cases: z
    .array(z.strictObject({ id: z.string(), family: z.enum(families), fingerprint: digestSchema }))
    .length(8),
});
export const reviewSchema = z.strictObject({
  fingerprint: digestSchema,
  decision: z.enum(["draft", "approved"]),
  cases: z
    .array(
      z.strictObject({
        id: z.string(),
        family: z.enum(families),
        split: z.enum(["development", "held-out"]),
        specification: z.string(),
        checks: z.array(z.string()),
      }),
    )
    .length(24),
  calibrationFingerprint: digestSchema,
});
export const hostSchema = z.strictObject({
  engine: z.enum(["codex", "claude-code"]),
  model: z.string().min(1),
  effort: z.enum(["medium", "high"]),
  cliVersion: z.string().min(1),
});
export const identitySchema = z.strictObject({
  commit: z.string(),
  tree: digestSchema,
  branch: z.string(),
});
export const learningOriginSchema = z.strictObject({
  preparationFingerprint: digestSchema,
  product: identitySchema,
  sourceFingerprint: digestSchema,
  resultFingerprints: z.array(digestSchema).length(3),
  reusedCalls: z.number().int().positive(),
  reason: z.string().min(20),
});
export const environmentSetSchema = z.strictObject({
  skills: armEnvironmentSchema,
  routing: armEnvironmentSchema,
  told: armEnvironmentSchema,
  deep: z.array(armEnvironmentSchema).length(3),
});
export const learningEvidenceSchema = z.strictObject({
  preparation: z.number().int().min(0).max(2),
  calls: z.array(learningCallSchema),
  completed: z.boolean(),
  published: z.array(
    z.strictObject({ key: z.string(), text: z.string(), scope: z.string(), status: z.string() }),
  ),
  missing: z.array(z.string()),
  pending: z.array(z.string()),
  unsupported: z.array(z.string()),
  inspection: z.enum(["review-required", "reviewed"]),
  assessmentFingerprint: digestSchema.optional(),
});
export const frozenSchema = z.strictObject({
  protocol: z.literal("preference-respect-v3"),
  version: z.literal(3),
  id: z.uuid(),
  experiment: z.enum(["learning", "routing"]),
  phase: z.enum(["preflight", "development", "qualification"]),
  benchmarkFingerprint: digestSchema,
  graderFingerprint: digestSchema,
  reviewFingerprint: digestSchema,
  bundleFingerprint: digestSchema,
  product: identitySchema,
  runtime: z.strictObject({ bun: z.string(), typescript: z.string() }),
  host: hostSchema,
  learner: learnerSchema.extend({ engine: z.literal("codex") }),
  templateDirectory: z.string(),
  templateFingerprint: digestSchema,
  privateBundle: z.string(),
  cases: z.array(caseSchema).min(1).max(24),
  learning: z.array(learningEvidenceSchema).max(3),
  learningOrigin: learningOriginSchema.optional(),
  environments: z.record(
    z.enum(["codex", "claude-code"]),
    z.record(z.enum(["atlas", "boreal"]), environmentSetSchema),
  ),
  routingEnvironments: z.record(
    z.enum(["codex", "claude-code"]),
    z.strictObject({ skills: armEnvironmentSchema, routing: armEnvironmentSchema }),
  ),
  repetitions: z.union([z.literal(1), z.literal(3)]),
  limits: z.strictObject({
    preparationCalls: z.number().int().nonnegative(),
    candidateCalls: z.number().int().nonnegative(),
    retryCalls: z.number().int().nonnegative(),
    maximumCalls: z.number().int().positive(),
    codeSeconds: z.literal(240),
    adviceSeconds: z.literal(120),
  }),
});
export const scopeSchema = z.strictObject({
  suiteFingerprint: digestSchema,
  host: hostSchema,
  phase: z.enum(["preflight", "development", "qualification"]),
  experiment: z.enum(["learning", "routing"]),
  maximumCalls: z.number().int().positive(),
  decision: z.literal("approved"),
});
export const diagnosticSchema = z.strictObject({
  stage: z.enum([
    "setup",
    "mount-create",
    "mount-attach",
    "execution",
    "verification",
    "mount-detach",
    "cleanup",
  ]),
  confirmedInfrastructure: z.boolean(),
  message: z.string(),
  details: z.string(),
});
export const attemptSchema = z.strictObject({
  number: z.number().int().min(1).max(2),
  status: z.enum(["running", "complete", "interrupted"]),
  calls: z.number().int().nonnegative(),
  record: runRecordSchema.nullable(),
  diagnostics: z.array(diagnosticSchema),
  checks: z.array(checkResultSchema),
});
export const cellSchema = z.strictObject({
  caseId: z.string(),
  setup: z.enum(setups),
  repetition: z.number().int().min(0).max(2),
  attempts: z.array(attemptSchema).max(2),
});
export const receiptSchema = z.strictObject({
  protocol: z.literal("preference-respect-v3"),
  suiteFingerprint: digestSchema,
  status: z.enum(["running", "complete", "interrupted"]),
  cells: z.array(cellSchema),
});
export type PreferenceCase = z.infer<typeof caseSchema>;
export type Family = (typeof families)[number];
export type Setup = (typeof setups)[number];
export type FrozenSuite = z.infer<typeof frozenSchema>;
export type Cell = z.infer<typeof cellSchema>;
export type Attempt = z.infer<typeof attemptSchema>;
export type Diagnostic = z.infer<typeof diagnosticSchema>;
export type Receipt = z.infer<typeof receiptSchema>;
