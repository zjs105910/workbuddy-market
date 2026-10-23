import { z } from "zod";

export const severities = ["high", "medium", "low"] as const;

export const categories = [
  "correctness",
  "security",
  "performance",
  "standards",
  "tests",
] as const;

export const findingSources = ["investigation", "rule", "toolchain"] as const;

const commitShaSchema = z.string().regex(/^[a-f0-9]{40}$/);

export const evidenceSources = ["code", "diff", "doc", "rule", "toolchain"] as const;

export const evidenceSchema = z.object({
  source: z.enum(evidenceSources),
  location: z.string().min(1).max(500),
  quote: z.string().min(1).max(300),
});

export type Evidence = z.infer<typeof evidenceSchema>;

export const findingSchema = z.object({
  path: z.string().min(1).max(500),
  line: z.number().int().positive(),
  severity: z.enum(severities),
  category: z.enum(categories),
  source: z.enum(findingSources),
  title: z.string().min(1).max(100),
  explanation: z.string().min(1).max(400),
  failureScenario: z.string().min(1).max(300),
  evidence: z.array(evidenceSchema).min(1).max(6),
  rule: z.string().max(300).nullable(),
  suggestion: z.string().max(300).nullable(),
  refutation: z.string().max(400),
  candidates: z.array(z.string().regex(/^[ST]\d{1,4}$/)).max(10),
});

export type Finding = z.infer<typeof findingSchema>;

export const analysisSchema = z.object({
  findings: z.array(findingSchema).max(20),
  dropped: z.array(z.object({ id: z.string().regex(/^[ST]\d{1,4}$/), reason: z.string().min(1).max(300) })).max(220),
});

export type Analysis = z.infer<typeof analysisSchema>;

export const pullFactsSchema = z.object({
  repository: z.string().regex(/^[\w.-]+\/[\w.-]+$/),
  number: z.number().int().positive().nullable(),
  title: z.string().max(1000),
  body: z.string().max(65_536),
  baseRefName: z.string().min(1).max(255),
  baseSha: commitShaSchema,
  headSha: commitShaSchema,
});

export type PullFacts = z.infer<typeof pullFactsSchema>;

export const lineRangeSchema = z.tuple([
  z.number().int().positive(),
  z.number().int().positive(),
]);

export type LineRange = z.infer<typeof lineRangeSchema>;

export const toolchainSummarySchema = z.object({
  stack: z.string(),
  tool: z.string(),
  status: z.enum(["ran", "skipped", "failed", "timed-out"]),
  detail: z.string().max(1000),
  newDiagnostics: z.number().int().nonnegative(),
});

export const reviewResultSchema = z.object({
  version: z.literal(1),
  pull: pullFactsSchema,
  model: z.string().min(1),
  findings: z.array(findingSchema).max(10),
  commentableLines: z.record(z.string(), z.array(lineRangeSchema)),
  skippedPaths: z.array(z.string().max(500)),
  toolchain: z.array(toolchainSummarySchema),
  dropped: z
    .array(z.object({ title: z.string().max(100), path: z.string().max(500), line: z.number().int().positive(), reason: z.string().max(300) }))
    .max(20),
  candidates: z.object({
    dropped: z
      .array(z.object({ id: z.string(), title: z.string().max(200), path: z.string().max(500), line: z.number().int().positive(), reason: z.string().max(300) }))
      .max(220),
    undecided: z.array(z.object({ id: z.string(), title: z.string().max(200), path: z.string().max(500), line: z.number().int().positive() })).max(220),
  }),
  rejections: z.array(z.string().max(600)).max(50),
  statistics: z.object({
    modelFindings: z.number().int().nonnegative(),
    droppedForEvidence: z.number().int().nonnegative(),
    correctionRound: z.enum(["none", "ran", "failed"]),
    certainRuleHits: z.number().int().nonnegative(),
    signalRuleHits: z.number().int().nonnegative(),
    durationMilliseconds: z.number().int().nonnegative(),
    costUsd: z.number().nonnegative().nullable(),
  }),
});

export type ReviewResult = z.infer<typeof reviewResultSchema>;
