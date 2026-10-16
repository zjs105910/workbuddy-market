import { z } from "zod";
import type { EngineId } from "./engineId";
import { readRootOwnedFile } from "./managedFile";
import {
  isSourceId,
  retiredSourceIds,
  sourceIds,
  type ShadowcloneConfig,
  type SourceId,
} from "./schema";

export type DistillationPolicy = "allowed" | "local-only" | "disabled";

export type ActionTier = "observe" | "draft" | "act";

export type ManagedPolicy = {
  readonly enabled: boolean;
  readonly allowedSources: readonly SourceId[];
  readonly allowedEngines: readonly EngineId[];
  readonly distillation: DistillationPolicy;
  readonly originScope: "strict";
  readonly blockedOrigins: readonly string[];
  readonly maxActionTier: ActionTier;
};

export const engineIds = [
  "claude-code",
  "codex",
  "cursor-agent",
  "antigravity",
  "anthropic-api",
  "openai-compatible",
  "pi",
] as const;

export const defaultManagedPolicy: ManagedPolicy = {
  enabled: true,
  allowedSources: sourceIds,
  allowedEngines: engineIds,
  distillation: "allowed",
  originScope: "strict",
  blockedOrigins: [],
  maxActionTier: "act",
};

const managedPolicySchema = z.object({
  enabled: z.boolean(),
  allowedSources: z
    .array(z.enum([...sourceIds, ...retiredSourceIds]))
    .transform((sources) => sources.filter(isSourceId)),
  allowedEngines: z.array(z.enum(engineIds)),
  distillation: z.enum(["allowed", "local-only", "disabled"]),
  originScope: z.literal("strict"),
  blockedOrigins: z.array(z.string()),
  maxActionTier: z.enum(["observe", "draft", "act"]),
});

export function parseManagedPolicy(value: unknown): ManagedPolicy {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error("Managed policy must be a JSON object");
  }

  const result = managedPolicySchema.safeParse(value);

  if (!result.success) {
    throw new Error("Managed policy has invalid or missing fields");
  }

  return result.data;
}

export function applyManagedPolicy(options: {
  readonly config: ShadowcloneConfig;
  readonly policy: ManagedPolicy;
}): ShadowcloneConfig {
  const sourceAllowed = (source: SourceId): boolean =>
    options.policy.enabled && options.policy.allowedSources.includes(source);

  return {
    ...options.config,
    sources: {
      "agent-context":
        options.config.sources["agent-context"] &&
        sourceAllowed("agent-context"),
      antigravity:
        options.config.sources.antigravity && sourceAllowed("antigravity"),
      "antigravity-workspaces":
        options.config.sources["antigravity-workspaces"] &&
        sourceAllowed("antigravity-workspaces"),
      "claude-memory":
        options.config.sources["claude-memory"] &&
        sourceAllowed("claude-memory"),
      "claude-rules":
        options.config.sources["claude-rules"] && sourceAllowed("claude-rules"),
      "claude-code":
        options.config.sources["claude-code"] && sourceAllowed("claude-code"),
      "claude-prompts":
        options.config.sources["claude-prompts"] &&
        sourceAllowed("claude-prompts"),
      codex: options.config.sources.codex && sourceAllowed("codex"),
      cursor: options.config.sources.cursor && sourceAllowed("cursor"),
      pi: options.config.sources.pi && sourceAllowed("pi"),
      "declared-rules":
        options.config.sources["declared-rules"] &&
        sourceAllowed("declared-rules"),
      "git-metadata":
        options.config.sources["git-metadata"] && sourceAllowed("git-metadata"),
      "github-writing":
        options.config.sources["github-writing"] &&
        sourceAllowed("github-writing"),
      "repository-manifests":
        options.config.sources["repository-manifests"] &&
        sourceAllowed("repository-manifests"),
      "skill-library":
        options.config.sources["skill-library"] &&
        sourceAllowed("skill-library"),
    },
    distillation: {
      ...options.config.distillation,
      automatic:
        options.config.distillation.automatic === true &&
        options.config.distillation.deep &&
        options.policy.enabled &&
        options.policy.distillation === "allowed",
      deep:
        options.config.distillation.deep &&
        options.policy.enabled &&
        options.policy.distillation !== "disabled",
    },
  };
}

export async function readManagedPolicy(
  managedConfigPath: string | null,
): Promise<ManagedPolicy> {
  if (managedConfigPath === null) {
    return defaultManagedPolicy;
  }

  if (!(await Bun.file(managedConfigPath).exists())) {
    return defaultManagedPolicy;
  }

  const value: unknown = JSON.parse(await readRootOwnedFile(managedConfigPath));

  return parseManagedPolicy(value);
}
