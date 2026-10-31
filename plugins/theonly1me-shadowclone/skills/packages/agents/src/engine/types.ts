import type { EngineId } from "@shadowclone/core";

export type { EngineId };

export type PermissionMode =
  | "acceptEdits"
  | "default"
  | "dontAsk"
  | "manual"
  | "plan"
  | "auto";

export const reasoningEfforts = [
  "low",
  "medium",
  "high",
  "xhigh",
  "max",
] as const;

export type ReasoningEffort = (typeof reasoningEfforts)[number];

export type PermissionDenial = {
  readonly toolName: string;
  readonly toolUseId: string | null;
};

export type EngineAction = {
  readonly tool: string;
  readonly path: string | null;
  readonly command?: string | null;
  readonly succeeded?: boolean | null;
  readonly requestSequence?: number;
  readonly resultSequence?: number | null;
};

export type EngineExecution =
  | {
      readonly purpose: "evaluation";
      readonly access?: "read" | "write";
      readonly blockedPaths?: readonly string[];
    }
  | { readonly purpose: "learning" }
  | { readonly purpose: "review"; readonly network?: boolean };

export type EngineRunOptions = {
  readonly prompt: string;
  readonly cwd: string;
  readonly execution: EngineExecution;
  readonly systemPromptFile?: string;
  readonly systemPrompt?: string;
  readonly thinking?: "off";
  readonly sessionId?: string;
  readonly model?: string;
  readonly reasoningEffort?: ReasoningEffort;
  readonly allowedTools?: readonly string[];
  readonly disallowedTools?: readonly string[];
  readonly permissionMode?: PermissionMode;
  readonly maxBudgetUsd?: number;
  readonly outputSchema?: unknown;
  readonly signal?: AbortSignal;
};

export type EngineRun = {
  readonly engine: EngineId;
  readonly resolvedModel?: string | null;
  readonly sessionId: string;
  readonly transcriptPath: string | null;
  readonly text: string;
  readonly structured: unknown;
  readonly costUsd: number | null;
  readonly durationMs: number;
  readonly turns: number;
  readonly isError: boolean;
  readonly permissionDenials: readonly PermissionDenial[];
  readonly actions: readonly EngineAction[];
  readonly errorMessage: string | null;
};

export type EngineRunner = (options: EngineRunOptions) => Promise<EngineRun>;

export type EngineAvailability = {
  readonly engine: EngineId;
  readonly installed: boolean;
  readonly authenticated: boolean;
};
