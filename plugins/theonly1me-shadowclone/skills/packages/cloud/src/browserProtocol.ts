import { z } from "zod";

export const setupPreviewInput = z.strictObject({
  repository: z.string().regex(/^[\w.-]+\/[\w.-]+$/),
  name: z.string().trim().min(1).max(100),
  skills: z
    .array(z.string().regex(/^[a-z0-9-]+$/))
    .min(1)
    .max(40),
});
export const setupPreviewSchema = z.object({
  id: z.uuid(),
  repository: z.string(),
  repositoryId: z.number(),
  owner: z.string(),
  appOwner: z.string(),
  fingerprint: z.string(),
  bytes: z.number(),
  files: z.array(z.object({ path: z.string(), content: z.string() })),
});
export const checklistSchema = z.array(
  z.object({
    key: z.string(),
    done: z.boolean(),
    title: z.string(),
    action: z.string(),
    links: z.array(z.object({ label: z.string(), url: z.url() })),
  }),
);
export const setupStateSchema = z.object({
  repository: z.string().nullable(),
  skills: z.array(z.string()).default([]),
  previewId: z.uuid().nullable().default(null),
  app: z.object({ name: z.string(), installUrl: z.url() }).nullable(),
  pullUrl: z.url().nullable(),
  checklist: checklistSchema.nullable().default(null),
});
export const accountSetupInput = z.strictObject({
  repository: z.string().regex(/^[\w.-]+\/[\w.-]+$/),
  botLogin: z.string().regex(/^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$/),
  approveSkills: z.boolean(),
  engine: z.enum(["claude", "codex"]).default("claude"),
  codexAuth: z.enum(["api-key", "plan"]).default("api-key"),
});
export const accountOutcomeSchema = z.discriminatedUnion("kind", [
  z.object({ kind: z.literal("needs-account"), login: z.string(), signupUrl: z.url() }),
  z.object({
    kind: z.literal("needs-approval"),
    skillsRepository: z.string(),
    files: z.array(z.object({ path: z.string(), bytes: z.number() })),
  }),
  z.object({
    kind: z.literal("configured"),
    pullUrl: z.url().nullable(),
    checklist: checklistSchema,
    warnings: z.array(z.string()).default([]),
  }),
]);
export const manifestViewSchema = z.object({
  action: z.url(),
  manifest: z.string(),
});
export const previewApprovalSchema = z.strictObject({ previewId: z.uuid() });
