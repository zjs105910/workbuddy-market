import type { EngineId } from "../engine/types";
import type { ProviderDefinition, ProviderId } from "./types";

export const providerDefinitions: readonly ProviderDefinition[] = [
  {
    id: "claude-code",
    captureSource: "claude-code",
    transcriptFormat: "jsonl",
    engine: {
      id: "claude-code",
      implemented: true,
      capabilities: {
        structuredOutput: "native",
        callerSessionId: true,
        maxBudgetUsd: true,
        granularToolPolicy: true,
        isolatedNoTools: true,
      },
    },
  },
  {
    id: "codex",
    captureSource: "codex",
    transcriptFormat: "jsonl",
    engine: {
      id: "codex",
      implemented: true,
      capabilities: {
        structuredOutput: "native",
        callerSessionId: false,
        maxBudgetUsd: false,
        granularToolPolicy: false,
        isolatedNoTools: true,
      },
    },
  },
  {
    id: "cursor",
    captureSource: "cursor",
    transcriptFormat: "sqlite",
    engine: {
      id: "cursor-agent",
      implemented: true,
      capabilities: {
        structuredOutput: "prompted",
        callerSessionId: false,
        maxBudgetUsd: false,
        granularToolPolicy: false,
        isolatedNoTools: true,
      },
    },
  },
  {
    id: "antigravity",
    captureSource: "antigravity",
    transcriptFormat: "jsonl",
    engine: {
      id: "antigravity",
      implemented: false,
      capabilities: {
        structuredOutput: "native",
        callerSessionId: false,
        maxBudgetUsd: false,
        granularToolPolicy: false,
        isolatedNoTools: false,
      },
    },
  },
  {
    id: "pi",
    captureSource: "pi",
    transcriptFormat: "jsonl",
    engine: {
      id: "pi",
      implemented: true,
      capabilities: {
        structuredOutput: "prompted",
        callerSessionId: false,
        maxBudgetUsd: false,
        granularToolPolicy: false,
        isolatedNoTools: true,
      },
    },
  },
];

export function getProvider(providerId: ProviderId): ProviderDefinition {
  const definition = providerDefinitions.find(
    (candidate) => candidate.id === providerId,
  );

  if (!definition) {
    throw new Error(`Provider definition is missing for ${providerId}`);
  }

  return definition;
}

export function getProviderByEngine(
  engineId: EngineId,
): ProviderDefinition | null {
  return (
    providerDefinitions.find(
      (definition) => definition.engine?.id === engineId,
    ) ?? null
  );
}
