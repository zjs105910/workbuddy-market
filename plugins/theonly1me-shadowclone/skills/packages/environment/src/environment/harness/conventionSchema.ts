import { z } from "zod";

export const conventionSchema = z.discriminatedUnion("kind", [
  z.strictObject({
    kind: z.literal("file-length"),
    maximumLines: z.number().int().min(10).max(10_000),
  }),
  z.strictObject({
    kind: z.literal("forbidden-text"),
    name: z.string().min(1),
    text: z.string().min(1),
  }),
  z.strictObject({ kind: z.literal("no-suppressions") }),
  z.strictObject({
    kind: z.literal("no-comments"),
    language: z.literal("typescript"),
  }),
]);

export type Convention = z.infer<typeof conventionSchema>;
