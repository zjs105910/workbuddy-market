import { z } from "zod";
import type { ReconciliationOutput } from "./types";

const sectionValues = ["engineering", "workflow", "boundaries"] as const;
const verdictValues = ["reinforces", "contradicts", "narrows"] as const;

const intentValues = [
  "preference",
  "correction",
  "approval",
  "additional-context",
  "cancellation",
  "unknown",
] as const;

const scopeValues = ["global", "repository"] as const;

const existingRuleSchema = z.strictObject({
  ruleToken: z.string().max(64),
  verdict: z.enum(verdictValues),
  observed: z.string().max(600),
  evidenceTokens: z.array(z.string().max(64)).max(20),
  proposedTitle: z.string().max(120),
  proposedBody: z.string().max(8192),
  axisChoiceToken: z.string().max(64),
});

const newRuleSchema = z.strictObject({
  title: z.string().max(120),
  body: z.string().max(8192),
  section: z.enum(sectionValues),
  observed: z.string().max(600),
  evidenceTokens: z.array(z.string().max(64)).max(20),
  rejectionToken: z.string().max(64),
});

const reconciliationSchema = z.strictObject({
  assessments: z
    .array(
      z.strictObject({
        evidenceToken: z.string().max(64),
        intent: z.enum(intentValues),
        durable: z.boolean(),
        explicit: z.boolean().optional().default(false),
        scope: z.enum(scopeValues),
      }),
    )
    .max(20)
    .optional(),
  existingRules: z.array(existingRuleSchema).max(24),
  newRules: z.array(newRuleSchema).max(8),
});

function normalize(value: string, maximumLength: number): string {
  return value
    .replaceAll("<!--", "")
    .replaceAll("-->", "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, maximumLength);
}

function normalizeBody(value: string): string {
  return value
    .replaceAll("<!--", "")
    .replaceAll("-->", "")
    .replaceAll("\r\n", "\n")
    .trim();
}

export const reconciliationOutputSchema = {
  type: "object",
  additionalProperties: false,
  required: ["existingRules", "newRules", "assessments"],
  properties: {
    assessments: {
      type: "array",
      maxItems: 20,
      items: {
        type: "object",
        additionalProperties: false,
        required: ["evidenceToken", "intent", "durable", "explicit", "scope"],
        properties: {
          evidenceToken: { type: "string", maxLength: 64 },
          intent: { type: "string", enum: intentValues },
          durable: { type: "boolean" },
          explicit: { type: "boolean" },
          scope: { type: "string", enum: scopeValues },
        },
      },
    },
    existingRules: {
      type: "array",
      maxItems: 24,
      items: {
        type: "object",
        additionalProperties: false,
        required: [
          "ruleToken",
          "verdict",
          "observed",
          "evidenceTokens",
          "proposedTitle",
          "proposedBody",
          "axisChoiceToken",
        ],
        properties: {
          ruleToken: { type: "string", maxLength: 64 },
          verdict: { type: "string", enum: verdictValues },
          observed: { type: "string", maxLength: 600 },
          evidenceTokens: {
            type: "array",
            maxItems: 20,
            items: { type: "string", maxLength: 64 },
          },
          proposedTitle: { type: "string", maxLength: 120 },
          proposedBody: { type: "string", maxLength: 8192 },
          axisChoiceToken: { type: "string", maxLength: 64 },
        },
      },
    },
    newRules: {
      type: "array",
      maxItems: 8,
      items: {
        type: "object",
        additionalProperties: false,
        required: [
          "title",
          "body",
          "section",
          "observed",
          "evidenceTokens",
          "rejectionToken",
        ],
        properties: {
          title: { type: "string", maxLength: 120 },
          body: { type: "string", maxLength: 8192 },
          section: { type: "string", enum: sectionValues },
          observed: { type: "string", maxLength: 600 },
          evidenceTokens: {
            type: "array",
            maxItems: 20,
            items: { type: "string", maxLength: 64 },
          },
          rejectionToken: { type: "string", maxLength: 64 },
        },
      },
    },
  },
} as const;

export function parseReconciliationOutput(
  value: unknown,
): ReconciliationOutput {
  const parsed = reconciliationSchema.safeParse(value);

  if (!parsed.success) {
    throw new Error("The engine returned an invalid reconciliation result");
  }

  return {
    assessments: parsed.data.assessments,
    existingRules: parsed.data.existingRules.map((entry) => ({
      ...entry,
      observed: normalize(entry.observed, 600),
      proposedTitle: normalize(entry.proposedTitle, 120),
      proposedBody: normalizeBody(entry.proposedBody),
    })),
    newRules: parsed.data.newRules.flatMap((entry) => {
      const title = normalize(entry.title, 120);
      const body = normalizeBody(entry.body);

      return title && body
        ? [{ ...entry, title, body, observed: normalize(entry.observed, 600) }]
        : [];
    }),
  };
}
