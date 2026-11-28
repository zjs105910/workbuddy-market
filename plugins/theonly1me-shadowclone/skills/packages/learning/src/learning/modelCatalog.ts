import type { z } from "zod";
import { readConfig, readEffectiveConfig, writeConfig } from "@shadowclone/core";
import { availablePiModels, detectEngine } from "@shadowclone/agents";
import type { ProjectPaths } from "@shadowclone/core";

import { learningModelChoiceSchema, type LearningModelChoice, type learningModelCatalogSchema } from "./modelCatalogSchema";
export { learningModelCatalogSchema, type LearningModelChoice } from "./modelCatalogSchema";

export async function learningModelCatalog(paths: ProjectPaths): Promise<z.infer<typeof learningModelCatalogSchema>> {
  const { config, policy } = await readEffectiveConfig({ configPath: paths.configFile, managedConfigPath: paths.managedConfigFile });
  if (!policy.enabled || policy.distillation !== "allowed") return { choices: [], selected: {} };
  const detection = await detectEngine({ purpose: "distill", allowedEngines: policy.allowedEngines });
  const choices: LearningModelChoice[] = [];
  for (const engine of detection.availability) {
    if (!engine.authenticated || !policy.allowedEngines.includes(engine.engine)) continue;
    if (engine.engine === "pi") {
      const models = await availablePiModels();
      choices.push(...models.map(model => ({ engine: "pi" as const, model: model.id, name: `Pi · ${model.name} (${model.id})` })));
    } else if (engine.engine === "claude-code" || engine.engine === "codex" || engine.engine === "cursor-agent") {
      choices.push({ engine: engine.engine, name: `${engine.engine} · harness default` });
    }
  }
  return { choices, selected: { engine: config.distillation.engine, model: config.distillation.model } };
}

export async function saveLearningModel(options: {
  readonly paths: ProjectPaths;
  readonly input: unknown;
}): Promise<void> {
  const selected = learningModelChoiceSchema.omit({ name: true }).parse(options.input);
  const catalog = await learningModelCatalog(options.paths);
  if (!catalog.choices.some(choice => choice.engine === selected.engine && choice.model === selected.model)) {
    throw new Error("The selected harness model is unavailable; configure it in your harness");
  }
  const config = await readConfig({ configPath: options.paths.configFile });
  const distillation = { deep: config.distillation.deep, automatic: config.distillation.automatic };
  await writeConfig({ configPath: options.paths.configFile, config: { ...config, distillation: { ...distillation, ...selected } } });
}
