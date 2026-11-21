import type { EngineId, EngineRunner, LearningExecutionLimits, ReasoningEffort } from "@shadowclone/agents";
import type { ProjectPaths } from "@shadowclone/core";
import type { GitRemoteReader } from "@shadowclone/sessions";
import type { ConfirmPrompt } from "./confirm";

export type LearnCommandOptions = {
  readonly deep: boolean;
  readonly dryRun: boolean;
  readonly apply: boolean;
  readonly engine?: EngineId;
  readonly model?: string;
  readonly reasoningEffort?: ReasoningEffort;
  readonly maximumCalls?: number;
};

function parseEngine(value: string): EngineId {
  if (value === "claude-code" || value === "codex" || value === "cursor-agent" || value === "pi") {
    return value;
  }

  throw new Error("Invalid learning engine");
}

function parseReasoningEffort(value: string): ReasoningEffort {
  if (
    value === "low" ||
    value === "medium" ||
    value === "high" ||
    value === "xhigh" ||
    value === "max"
  ) {
    return value;
  }

  throw new Error("Invalid learning reasoning effort");
}

function parseMaximumCalls(value: string): number {
  const maximumCalls = Number(value);

  if (!Number.isSafeInteger(maximumCalls) || maximumCalls < 1) {
    throw new Error("Invalid learning call ceiling");
  }

  return maximumCalls;
}

function optionValue(options: {
  readonly arguments_: readonly string[];
  readonly position: number;
  readonly flag: string;
}): string {
  const value = options.arguments_[options.position + 1];

  if (!value || value.startsWith("--")) {
    throw new Error(`${options.flag} requires a value`);
  }

  return value;
}

export function parseLearnOptions(arguments_: readonly string[]): LearnCommandOptions | null {
  let deep = false;
  let dryRun = false;
  let apply = false;

  let engine: EngineId | undefined;
  let model: string | undefined;
  let reasoningEffort: ReasoningEffort | undefined;
  let maximumCalls: number | undefined;

  const seen = new Set<string>();

  for (let position = 0; position < arguments_.length; position += 1) {
    const argument = arguments_[position];

    if (!argument?.startsWith("--") || seen.has(argument)) {
      return null;
    }

    seen.add(argument);

    if (argument === "--deep") {
      deep = true;
    } else if (argument === "--dry-run") {
      dryRun = true;
    } else if (argument === "--apply") {
      apply = true;
    } else if (argument === "--engine") {
      const value = optionValue({ arguments_, position, flag: argument });

      engine = parseEngine(value);
      position += 1;
    } else if (argument === "--model") {
      model = optionValue({ arguments_, position, flag: argument });
      position += 1;
    } else if (argument === "--reasoning-effort") {
      const value = optionValue({ arguments_, position, flag: argument });

      reasoningEffort = parseReasoningEffort(value);
      position += 1;
    } else if (argument === "--max-calls") {
      const value = optionValue({ arguments_, position, flag: argument });

      maximumCalls = parseMaximumCalls(value);
      position += 1;
    } else {
      return null;
    }
  }

  if (apply && !deep) {
    throw new Error("learn --apply requires --deep");
  }

  if (apply && dryRun) {
    throw new Error("learn --apply cannot be combined with --dry-run");
  }

  if ((engine || model || reasoningEffort || maximumCalls) && !deep) {
    throw new Error("Learning engine options require --deep");
  }

  return {
    deep,
    dryRun,
    apply,
    ...(engine ? { engine } : {}),
    ...(model ? { model } : {}),
    ...(reasoningEffort ? { reasoningEffort } : {}),
    ...(maximumCalls === undefined ? {} : { maximumCalls }),
  };
}

export type LearnExecutionOptions = {
  readonly workingDirectory?: string;
  readonly configPath?: string;
  readonly databasePath?: string;
  readonly paths?: ProjectPaths;
  readonly readRemote?: GitRemoteReader;
  readonly deep?: boolean;
  readonly dryRun?: boolean;
  readonly apply?: boolean;
  readonly runner?: EngineRunner;
  readonly engine?: EngineId;
  readonly model?: string;
  readonly reasoningEffort?: ReasoningEffort;
  readonly maximumCalls?: number;
  readonly limits?: LearningExecutionLimits;
  readonly confirm?: ConfirmPrompt;
  readonly writeLine?: (line: string) => void;
  readonly managedConfigPath?: string | null;
};
