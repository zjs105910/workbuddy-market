import type { EngineRun } from "../types";

export const nativeModels = {
  "claude-code": "claude-opus-5-5",
  codex: "gpt-6-sol",
} as const;

export type NativeEngine = keyof typeof nativeModels;

export type NativeEngineOptions = {
  readonly engine: NativeEngine;
  readonly prompt: string;
  readonly directory: string;
  readonly homeDirectory: string;
  readonly memoryEnabled: boolean;
  readonly access: "read" | "write" | "none";
  readonly blockedPaths: readonly string[];
  readonly protectedPaths: readonly string[];
  readonly writablePaths?: readonly string[];
  readonly model?: string;
  readonly effort?: "medium" | "high";
  readonly toolDirectory?: string;
  readonly signal?: AbortSignal;
  readonly outputSchema?: unknown;
  readonly expectedCliVersion?: string;
  readonly learningModel?: "gpt-6-sol";
  readonly persistSession?: boolean;
  readonly resumeSessionId?: string;
  readonly debugTransport?: (output: { readonly stdout: string; readonly stderr: string }) => Promise<void>;
};

export type NativeEngineRun = EngineRun & {
  readonly cliVersion: string;
  readonly resumableSessionId: string | null;
  readonly usage: {
    readonly inputTokens: number;
    readonly cachedInputTokens: number;
    readonly outputTokens: number;
  } | null;
};

export type NativeEngineRunner = (
  options: NativeEngineOptions,
) => Promise<NativeEngineRun>;
