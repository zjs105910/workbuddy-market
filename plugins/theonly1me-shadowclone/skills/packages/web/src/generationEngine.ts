import { readEffectiveConfig } from "@shadowclone/core";
import { detectEngine, getProviderByEngine, fastTier } from "@shadowclone/agents";
import type { EngineId, EngineRunner } from "@shadowclone/agents";
import { selectLearningPreferences } from "@shadowclone/learning";
import type { BuildContext } from "@shadowclone/environment";

export type GenerationEngine = {
  readonly engine: EngineId;
  readonly runner: EngineRunner;
  readonly model?: string;
};

export type GenerationTier = "saved" | "fast";

export async function allowedGenerationEngines(context: BuildContext) {
  const { policy } = await readEffectiveConfig({
    configPath: context.paths.configFile,
    managedConfigPath: context.paths.managedConfigFile,
  });

  if (!policy.enabled || policy.distillation !== "allowed") {
    throw new Error("Managed policy does not allow model generation");
  }

  return policy.allowedEngines;
}

export async function generationEngine(
  options: BuildContext & { readonly engine?: GenerationEngine; readonly tier?: GenerationTier },
): Promise<GenerationEngine> {
  const allowed = await allowedGenerationEngines(options);
  const { config } = await readEffectiveConfig({ configPath: options.paths.configFile, managedConfigPath: options.paths.managedConfigFile });
  const preferences = selectLearningPreferences({ explicit: options.engine, saved: config.distillation });
  const detected = options.engine
    ? null
    : await detectEngine({
        purpose: "distill",
        allowedEngines: allowed,
        model: preferences.model,
        preferredEngine: preferences.engine,
      });

  const engine = options.engine?.engine ?? detected?.selectedEngine;
  const runner = options.engine?.runner ?? detected?.runner;

  if (!engine || !runner || !allowed.includes(engine)) {
    throw new Error("Sign in to a supported coding-agent CLI to use AI");
  }

  if (options.tier === "fast") {
    const tier = fastTier({ engine, savedModel: preferences.model });
    const model = tier.model ?? undefined;
    const effort = tier.reasoningEffort ?? undefined;

    return {
      engine,
      ...(model ? { model } : {}),
      runner: (run) =>
        runner({
          ...run,
          ...(model ? { model } : {}),
          ...(effort ? { reasoningEffort: effort } : {}),
          ...(tier.thinking ? { thinking: tier.thinking } : {}),
          ...(tier.systemPrompt ? { systemPrompt: tier.systemPrompt } : {}),
        }),
    };
  }

  const model = preferences.model;
  return { engine, model, runner: model ? run => runner({ ...run, model }) : runner };
}

export function generationLimits(engine: EngineId): string {
  return getProviderByEngine(engine)?.engine?.capabilities.maxBudgetUsd
    ? "One call, 60 seconds, maximum $0.25. Your existing provider account is used."
    : "One call, 60 seconds. This provider has no enforceable dollar cap; charges use your existing account.";
}
