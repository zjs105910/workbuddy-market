import { z } from "zod";

export const repositorySchema = z.object({
  id: z.number().int().positive(),
  full_name: z.string().regex(/^[\w.-]+\/[\w.-]+$/),
  default_branch: z.string().min(1),
  owner: z.object({ login: z.string(), type: z.enum(["User", "Organization"]).default("User") }),
  permissions: z.object({ admin: z.boolean() }),
});

export type Repository = z.infer<typeof repositorySchema>;

export const identitySchema = z.discriminatedUnion("kind", [
  z.strictObject({ kind: z.literal("app"), appId: z.number().int().positive() }),
  z.strictObject({ kind: z.literal("account") }),
]);

export type Identity = z.infer<typeof identitySchema>;

export const accountLoginPattern = /^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$/;

export const cloneSchema = z
  .strictObject({
    repositoryId: z.number().int().positive(),
    repository: z.string().regex(/^[\w.-]+\/[\w.-]+$/),
    defaultBranch: z.string().min(1),
    owner: z.string().regex(/^[\w-]+$/),
    identity: identitySchema,
    botId: z.number().int().positive(),
    botLogin: z.string().regex(/^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})(?:\[bot\])?$/),
    skillsRepository: z.string().regex(/^[\w.-]+\/[\w.-]+$/),
    requesters: z.array(z.string().regex(/^[\w-]+$/)).min(1),
    reviewerBots: z.array(z.string().regex(/^[\w-]+\[bot\]$/)),
    maximumRuns: z.number().int().min(1).max(100).default(10),
    reviewModel: z.string().regex(/^[\w.-]+$/).default("claude-opus-5-5"),
    reviewNetwork: z.boolean().default(true),
    engine: z.enum(["claude", "codex"]).default("claude"),
    codexAuth: z.enum(["api-key", "plan"]).default("api-key"),
  })
  .refine((clone) => (clone.identity.kind === "app") === clone.botLogin.endsWith("[bot]"), {
    message: "An App bot login ends with [bot], and a machine account login does not.",
    path: ["botLogin"],
  })
  .refine((clone) => clone.codexAuth === "api-key" || (clone.engine === "codex" && clone.identity.kind === "account"), {
    message: "A ChatGPT plan login needs Codex and a machine account bot.",
    path: ["codexAuth"],
  });

export type Clone = z.infer<typeof cloneSchema>;

export type GithubRequest = (
  route: string,
  parameters?: Record<string, unknown>,
) => Promise<{ data: unknown }>;

export type EventContext = {
  readonly eventName: string;
  readonly actor: string;
  readonly runId: number;
  readonly repo: { readonly owner: string; readonly repo: string };
  readonly payload: Record<string, unknown>;
};

export type Delivery = {
  readonly fingerprint: string;
  readonly native: string;
  readonly files: readonly {
    readonly path: string;
    readonly content: string;
    readonly mode: number;
  }[];
  readonly skills: readonly string[];
};
