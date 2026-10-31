import { z } from "zod";
import type { ProjectPaths } from "@shadowclone/core";

export const buildScopeSchema = z.enum(["global", "private", "shared"]);
const nameSchema = z
  .string()
  .regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/)
  .max(48);
export const customSkillSchema = z.strictObject({
  name: nameSchema,
  description: z.string().trim().min(1).max(300),
  body: z.string().trim().min(1).max(24_000),
});

export const buildInputSchema = z.strictObject({
  scope: buildScopeSchema,
  choices: z.record(z.string().max(128), z.boolean()),
  edits: z
    .record(z.string().max(128), z.string().min(1).max(48_000))
    .default({}),
  custom: z.array(customSkillSchema).max(40).default([]),
});

export const buildDefinitionSchema = buildInputSchema.extend({
  directory: z.string(),
  id: z.string(),
});

export type BuildInput = z.infer<typeof buildInputSchema>;

export type BuildDefinition = z.infer<typeof buildDefinitionSchema>;

export type BuildScope = BuildInput["scope"];

export type BuildContext = {
  readonly paths: ProjectPaths;
  readonly cwd: string;
};
