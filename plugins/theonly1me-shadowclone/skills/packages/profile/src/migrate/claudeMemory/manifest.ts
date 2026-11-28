import { z } from "zod";
import type { ClaudeMemoryManifest } from "./types";

const reasonSchema = z.enum([
  "skill-covered",
  "repo-covered",
  "stale",
  "synthetic",
  "one-off",
  "duplicate",
  "user-rejected",
]);

const manifestSchema = z.strictObject({
  schema: z.literal(1),
  repositoryId: z.string().min(1),
  sourceDirectory: z.string().min(1),
  createdAt: z.iso.datetime(),
  files: z
    .array(
      z.strictObject({
        filename: z.string().min(1),
        hash: z.string().regex(/^[a-f0-9]{64}$/),
        bytes: z.number().int().nonnegative(),
        kind: z.enum(["user", "feedback", "reference", "project", "index"]),
        disposition: z.enum([
          "rule",
          "reference",
          "recall-reference",
          "review-required",
          "covered",
          "project-preserved",
          "index-rebuilt",
          "archive-only",
        ]),
        reason: reasonSchema.optional(),
        destination: z.string().min(1).optional(),
      }),
    )
    .max(256),
});

export function parseClaudeMemoryManifest(text: string): ClaudeMemoryManifest {
  try {
    return manifestSchema.parse(JSON.parse(text));
  } catch {
    throw new Error("Claude memory migration manifest is invalid");
  }
}

export function renderClaudeMemoryManifest(
  manifest: ClaudeMemoryManifest,
): string {
  return `${JSON.stringify(manifest, null, 2)}\n`;
}
