import { z } from "zod";
import { constellationSchema } from "@shadowclone/builds/browser";
import { buildInputSchema, buildScopeSchema } from "@shadowclone/environment/browser";

export const itemSchema = z.strictObject({
  id: z.string(),
  name: z.string(),
  title: z.string(),
  description: z.string(),
  text: z.string(),
  kind: z.enum(["preference", "skill"]),
  category: z.string().nullable(),
  section: z.string().nullable(),
  axis: z.string().nullable(),
  alwaysOn: z.boolean(),
  owner: z.enum(["packaged", "managed", "user", "provider"]),
});

export const buildViewSchema = z.strictObject({
  scope: buildScopeSchema,
  input: buildInputSchema,
  inherited: z.record(z.string(), z.boolean()),
  locked: z.record(z.string(), z.boolean()),
  items: z.array(itemSchema),
  constellation: constellationSchema,
  requirements: z.array(z.string()),
  libraryEnabled: z.boolean(),
  migrationRequired: z.boolean(),
  revisionId: z.string().nullable(),
});

export const previewSchema = z.strictObject({
  id: z.uuid(),
  changes: z.array(
    z.strictObject({
      path: z.string(),
      before: z.string().nullable(),
      after: z.string().nullable(),
      internal: z.boolean(),
    }),
  ),
  warnings: z.array(z.string()),
});

export const applyResultSchema = z.strictObject({
  revisionId: z.string().nullable(),
});

export type BuildView = z.infer<typeof buildViewSchema>;

export type BrowserItem = z.infer<typeof itemSchema>;

export type BuildPreview = z.infer<typeof previewSchema>;
