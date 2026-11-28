import { z } from "zod";

export const patternSchema = z.string().min(1).max(400).refine((value) => {
  try {
    new RegExp(value, "iu");
    return true;
  } catch {
    return false;
  }
}, "Expected a valid regular expression");

const turnSchema = z.number().int().min(0).max(3);
const extractSchema = z.enum(["reply", "all"]);
const conversationSchema = z.array(z.strictObject({
  role: z.enum(["user", "assistant"]),
  text: z.string().min(1).max(8000),
})).min(2);

export const calibrationSchema = z.strictObject({
  label: z.enum(["pass", "fail", "boundary"]),
  conversation: conversationSchema,
});

const base = {
  id: z.string().regex(/^[a-z][a-z0-9-]*$/),
  keyItem: z.string().regex(/^[a-z][a-z0-9-]*$/),
};

export const checkSchema = z.discriminatedUnion("kind", [
  z.strictObject({ ...base, kind: z.literal("no-added-comments") }),
  z.strictObject({ ...base, kind: z.literal("no-unsafe-types") }),
  z.strictObject({ ...base, kind: z.literal("max-file-lines"), limit: z.number().int().min(20).max(2000) }),
  z.strictObject({ ...base, kind: z.literal("options-object") }),
  z.strictObject({ ...base, kind: z.literal("identifiers"), denylist: z.array(z.string().min(1)).max(100) }),
  z.strictObject({ ...base, kind: z.literal("test-first"), turn: turnSchema, testPattern: patternSchema }),
  z.strictObject({ ...base, kind: z.literal("mutation-proof"), turn: turnSchema, testPattern: patternSchema }),
  z.strictObject({ ...base, kind: z.literal("no-git-writes"), untilTurn: turnSchema.optional() }),
  z.strictObject({ ...base, kind: z.literal("commit-proposal"), turn: turnSchema }),
  z.strictObject({
    ...base, kind: z.literal("commit-shape"), afterTurn: turnSchema, subjectOnly: z.boolean(),
    subject: patternSchema, forbidden: z.array(patternSchema).max(20),
  }),
  z.strictObject({
    ...base, kind: z.literal("file-patterns"), files: patternSchema, forbidden: z.array(patternSchema).min(1).max(20),
  }),
  z.strictObject({
    ...base, kind: z.literal("pull-request"), aspect: z.enum(["title", "body", "checklist", "draft"]),
    forbidden: z.array(patternSchema).max(20), checklistHeading: z.string().min(1).max(80).optional(),
  }),
  z.strictObject({ ...base, kind: z.literal("max-words"), turn: turnSchema, maximum: z.number().int().min(1).max(2000) }),
  z.strictObject({
    ...base, kind: z.literal("patterns"), turn: turnSchema, extract: extractSchema,
    required: z.array(patternSchema).max(20), forbidden: z.array(patternSchema).max(20),
  }),
  z.strictObject({
    ...base, kind: z.literal("sentence-count"), turn: turnSchema, extract: extractSchema,
    maximum: z.number().int().min(1).max(50),
  }),
  z.strictObject({
    ...base, kind: z.literal("judged"), turn: turnSchema, requirement: z.string().min(10).max(2000),
    calibration: z.array(calibrationSchema).min(3).max(6),
  }),
]);

export const verdictSchema = z.enum(["pass", "fail", "not-applicable", "unknown"]);
export const checkResultSchema = z.strictObject({
  id: z.string(),
  keyItem: z.string(),
  verdict: verdictSchema,
  evidence: z.string().max(2000),
});

export type StudyCheck = z.infer<typeof checkSchema>;
export type StudyVerdict = z.infer<typeof verdictSchema>;
export type StudyCheckResult = z.infer<typeof checkResultSchema>;
export type Calibration = z.infer<typeof calibrationSchema>;
