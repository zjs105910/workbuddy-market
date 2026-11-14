import { z } from "zod";
import type { EngineId } from "./engineId";

export const sourceIds = [
  "agent-context",
  "antigravity",
  "antigravity-workspaces",
  "claude-memory",
  "claude-rules",
  "claude-code",
  "claude-prompts",
  "codex",
  "cursor",
  "declared-rules",
  "git-metadata",
  "github-writing",
  "repository-manifests",
  "pi",
  "skill-library",
] as const;

export type SourceId = (typeof sourceIds)[number];

export const retiredSourceIds = ["shell"] as const;

export function isSourceId(value: string): value is SourceId {
  return sourceIds.some((sourceId) => sourceId === value);
}

function isRetiredSourceId(value: string): boolean {
  return retiredSourceIds.some((sourceId) => sourceId === value);
}

export type SourceSettings = {
  readonly [Source in SourceId]: boolean;
};

export type ShadowcloneConfig = {
  readonly schemaVersion: 1;
  readonly sources: SourceSettings;
  readonly distillation: {
    readonly deep: boolean;
    readonly automatic?: boolean;
    readonly engine?: EngineId;
    readonly model?: string;
  };
};

export const defaultConfig: ShadowcloneConfig = {
  schemaVersion: 1,
  sources: {
    "agent-context": false,
    antigravity: false,
    "antigravity-workspaces": false,
    "claude-memory": false,
    "claude-rules": false,
    "claude-code": false,
    "claude-prompts": false,
    codex: false,
    cursor: false,
    pi: false,
    "declared-rules": false,
    "git-metadata": false,
    "github-writing": false,
    "repository-manifests": false,
    "skill-library": false,
  },
  distillation: {
    deep: false,
    automatic: false,
  },
};

const sourcesSchema = z.strictObject({
  "agent-context": z.boolean().optional().default(false),
  antigravity: z.boolean().optional().default(false),
  "antigravity-workspaces": z.boolean().optional().default(false),
  "claude-memory": z.boolean().optional().default(false),
  "claude-rules": z.boolean().optional().default(false),
  "claude-code": z.boolean(),
  "claude-prompts": z.boolean(),
  codex: z.boolean(),
  cursor: z.boolean(),
  pi: z.boolean().optional().default(false),
  "declared-rules": z.boolean().optional().default(false),
  "git-metadata": z.boolean().optional().default(false),
  "github-writing": z.boolean().optional().default(false),
  "repository-manifests": z.boolean().optional().default(false),
  "skill-library": z.boolean().optional().default(false),
});

const requiredCoreSourceIds = [
  "claude-code",
  "claude-prompts",
  "codex",
  "cursor",
] as const;

function hasUnknownKey(issues: readonly z.core.$ZodIssue[]): boolean {
  return issues.some((issue) => issue.code === "unrecognized_keys");
}

function parseSources(value: unknown): SourceSettings {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(
      "Config sources must contain every supported source and no unknown sources",
    );
  }

  const sources = Object.fromEntries(
    Object.entries(value).filter(([key]) => !isRetiredSourceId(key)),
  );
  const result = sourcesSchema.safeParse(sources);

  if (!result.success) {
    const missingCore = requiredCoreSourceIds.some((key) => !(key in sources));

    if (hasUnknownKey(result.error.issues) || missingCore) {
      throw new Error(
        "Config sources must contain every supported source and no unknown sources",
      );
    }

    throw new Error("Every config source setting must be a boolean");
  }

  return result.data;
}

const distillationSchema = z.strictObject({
  deep: z.boolean(),
  automatic: z.boolean().optional().default(false),
  engine: z.enum(["claude-code", "codex", "cursor-agent", "pi"]).optional(),
  model: z.string().trim().min(1).optional(),
});

function parseDistillation(value: unknown): ShadowcloneConfig["distillation"] {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(
      "Config distillation must contain deep and optional automatic settings",
    );
  }

  const result = distillationSchema.safeParse(value);

  if (!result.success) {
    if (hasUnknownKey(result.error.issues) || !("deep" in value)) {
      throw new Error(
        "Config distillation must contain deep and optional automatic settings",
      );
    }

    throw new Error(
      "Config distillation.deep and distillation.automatic must be booleans",
    );
  }

  return result.data;
}

const configSchema = z.strictObject({
  "schema-version": z.literal(1),
  sources: z.unknown(),
  distillation: z.unknown(),
  repo: z.unknown().optional(),
});

export function parseConfig(value: unknown): ShadowcloneConfig {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error("Config must contain only supported top-level settings");
  }

  const result = configSchema.safeParse(value);

  if (!result.success) {
    const wrongSchemaVersion =
      "schema-version" in value &&
      result.error.issues.some((issue) =>
        issue.path.includes("schema-version"),
      );

    throw new Error(
      wrongSchemaVersion
        ? "Config schema-version must be 1"
        : "Config must contain only supported top-level settings",
    );
  }

  return {
    schemaVersion: 1,
    sources: parseSources(result.data.sources),
    distillation: parseDistillation(result.data.distillation),
  };
}
