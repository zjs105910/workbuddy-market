import {
  createLearningExecution,
  detectEngine,
  type EngineId,
  type EngineRunner,
  type LearningExecution,
} from "@shadowclone/agents";

export async function resolveLearningExecution(options: {
  readonly runner?: EngineRunner;
  readonly engine?: EngineId;
  readonly model?: string;
  readonly execution?: LearningExecution;
  readonly allowedEngines: readonly EngineId[];
}): Promise<{
  readonly engine: EngineId;
  readonly runner: EngineRunner;
  readonly execution: LearningExecution;
}> {
  const detection = options.runner
    ? null
    : await detectEngine({
        purpose: "distill",
        allowedEngines: options.allowedEngines,
        preferredEngine: options.engine,
        model: options.model,
      });

  const selectedRunner = options.runner ?? detection?.runner;
  const runner = selectedRunner && options.model ? (run: Parameters<EngineRunner>[0]) => selectedRunner({ ...run, model: options.model }) : selectedRunner;
  const engine = options.engine ?? detection?.selectedEngine;

  if (!runner || !engine) {
    throw new Error("No authenticated learning engine is available");
  }
  if (!options.allowedEngines.includes(engine)) throw new Error("Managed policy blocks the selected learning engine");

  const execution =
    options.execution ?? createLearningExecution({ engine, runner });

  return { engine, runner, execution };
}
