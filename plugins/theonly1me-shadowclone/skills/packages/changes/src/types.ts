import { z } from "zod";

export const revisionSchema = z.strictObject({
  id: z.uuid(),
  kind: z.enum(["profile", "skill", "harness", "environment"]),
  root: z.string().min(1),
  createdAt: z.number(),
  status: z.enum(["prepared", "applied"]),
  changes: z
    .array(
      z.strictObject({
        relativePath: z.string().min(1),
        before: z.string().nullable(),
        after: z.string().nullable(),
        encoding: z.enum(["utf8", "base64"]).optional(),
        mode: z.number().int().min(0).max(511).optional(),
      }),
    )
    .max(256),
});
export type LocalRevision = z.infer<typeof revisionSchema>;
export type FileUpdate = {
  readonly filePath: string;
  readonly next: string | null;
  readonly previous?: string | null;
  readonly encoding?: "utf8" | "base64";
  readonly mode?: number;
};
