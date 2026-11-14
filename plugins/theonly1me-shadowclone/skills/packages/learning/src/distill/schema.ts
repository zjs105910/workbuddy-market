import { z } from "zod";
import type { ProfileSection } from "@shadowclone/profile";

export type DistilledRule = {
  readonly title: string;
  readonly body: string;
  readonly section: ProfileSection;
  readonly sources?: readonly number[];
};

export const distillationMergeOutputSchema = {
  type: "object",
  additionalProperties: false,
  required: ["rules", "dropped"],
  properties: {
    dropped: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        required: ["index", "reason"],
        properties: {
          index: { type: "integer" },
          reason: { type: "string", maxLength: 200 },
        },
      },
    },
    rules: {
      type: "array",
      maxItems: 8,
      items: {
        type: "object",
        additionalProperties: false,
        required: ["title", "body", "section", "sources"],
        properties: {
          title: { type: "string", maxLength: 120 },
          body: { type: "string", maxLength: 600 },
          section: {
            type: "string",
            enum: ["engineering", "workflow", "boundaries"],
          },
          sources: {
            type: "array",
            minItems: 1,
            items: { type: "integer" },
          },
        },
      },
    },
  },
} as const;

const distilledRuleItemSchema = z.object({
  title: z.string(),
  body: z.string(),
  section: z.enum(["engineering", "workflow", "boundaries"]),
  sources: z.array(z.number().int().nonnegative()).optional(),
});

function normalizeText(value: string, maxLength: number): string {
  return value
    .replaceAll("<!--", "")
    .replaceAll("-->", "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, maxLength);
}

const mergeDropSchema = z.object({
  index: z.number().int().nonnegative(),
  reason: z.string(),
});

export function parseMergeDrops(value: unknown): readonly { index: number; reason: string }[] {
  if (typeof value !== "object" || value === null || !("dropped" in value)) {
    return [];
  }

  const entries = Array.isArray(value.dropped) ? value.dropped : [];

  return entries.flatMap((entry) => {
    const parsed = mergeDropSchema.safeParse(entry);
    const reason = parsed.success ? normalizeText(parsed.data.reason, 200) : "";

    return parsed.success && reason ? [{ index: parsed.data.index, reason }] : [];
  });
}

export function parseDistilledRules(value: unknown): readonly DistilledRule[] {
  if (
    typeof value !== "object" ||
    value === null ||
    !("rules" in value) ||
    !Array.isArray(value.rules)
  ) {
    throw new Error("The engine returned an invalid distillation result");
  }

  return value.rules.flatMap((entry) => {
    const parsed = distilledRuleItemSchema.safeParse(entry);

    if (!parsed.success) {
      return [];
    }

    const title = normalizeText(parsed.data.title, 120);
    const body = normalizeText(parsed.data.body, 600);

    if (!title || !body) {
      return [];
    }

    return [
      {
        title,
        body,
        section: parsed.data.section,
        ...(parsed.data.sources ? { sources: parsed.data.sources } : {}),
      },
    ];
  });
}
