import { z } from "zod";
import type { ProjectPaths } from "@shadowclone/core";
import type { GitRemoteReader } from "@shadowclone/sessions";

export const integrationAgentSchema = z.enum([
  "claude-code",
  "codex",
  "cursor",
  "antigravity",
  "pi",
]);
export type IntegrationAgent = z.infer<typeof integrationAgentSchema>;
export const integrationScopeSchema = z.enum(["global", "repository"]);
export type IntegrationScope = z.infer<typeof integrationScopeSchema>;

export const integrationSchema = z.strictObject({
  id: z.uuid(),
  agent: integrationAgentSchema,
  scope: integrationScopeSchema,
  directory: z.string().min(1),
  userDirectory: z.string().min(1),
  codexInstructions: z
    .enum(["AGENTS.md", "AGENTS.override.md"])
    .default("AGENTS.md"),
  files: z.array(
    z.strictObject({
      relativePath: z.string().min(1),
      kind: z.enum(["instructions", "skill", "hooks", "extension"]),
      fingerprint: z.string(),
      created: z.boolean(),
    }),
  ),
  excludes: z.array(z.string()),
  deliveredAt: z.number().nullable(),
});
export type Integration = z.infer<typeof integrationSchema>;
export type IntegrationFile = Integration["files"][number];
export type IntegrationOptions = {
  readonly paths?: ProjectPaths;
  readonly configPath?: string;
  readonly managedConfigPath?: string | null;
  readonly readRemote?: GitRemoteReader;
};
