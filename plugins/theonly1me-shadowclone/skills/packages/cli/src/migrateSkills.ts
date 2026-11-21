import {
  readConfig,
  readEffectiveConfig,
  setSourceEnabled,
  writeConfig,
  projectPaths,
} from "@shadowclone/core";
import {
  createLearningExecution,
  detectEngine,
  type EngineId,
} from "@shadowclone/agents";
import {
  activateEnvironment,
  belongsToScope,
  learningScopes,
  prepareEnvironmentMigration,
} from "@shadowclone/environment";
import { selectLearningPreferences, updateLearningEnvironment } from "@shadowclone/learning";

export async function handleSkillsMigration(options: {
  readonly command: string | undefined;
  readonly arguments: readonly string[];
}): Promise<boolean> {
  if (options.command !== "migrate" || options.arguments[0] !== "skills") {
    return false;
  }

  let apply = false;
  let automatic = false;
  let memory = false;
  let activate = false;
  let activateOnly = false;

  const repositories: string[] = [];

  let engine: EngineId | undefined;
  let model: string | undefined;

  for (let position = 1; position < options.arguments.length; position += 1) {
    const argument = options.arguments[position];

    if (argument === "--apply") {
      apply = true;
    } else if (argument === "--automatic") {
      automatic = true;
    } else if (argument === "--memory") {
      memory = true;
    } else if (argument === "--activate") {
      activate = true;
    } else if (argument === "--activate-only") {
      activateOnly = true;
    } else if (argument === "--repo" && options.arguments[position + 1]) {
      repositories.push(options.arguments[++position] ?? "");
    } else if (argument === "--model" && options.arguments[position + 1]) {
      model = options.arguments[++position];
    } else if (argument === "--engine" && options.arguments[position + 1]) {
      const value = options.arguments[++position];

      if (
        value !== "claude-code" &&
        value !== "codex" &&
        value !== "cursor-agent" &&
        value !== "pi"
      ) {
        throw new Error("Unsupported learning engine");
      }

      engine = value;
    } else {
      throw new Error(
        "Use migrate skills [--apply] [--automatic] [--memory] [--activate] [--repo <path>] [--engine <id>] [--model <id>]",
      );
    }
  }

  const state = await prepareEnvironmentMigration({
    paths: projectPaths,
    repositories: repositories.length ? repositories : [process.cwd()],
    automatic,
    apply,
  });

  console.log(
    `${state.records.length} retained learning(s), ${state.repositories.length} registered repository scope(s).`,
  );

  const scopes = learningScopes({ paths: projectPaths, state });
  const unresolved = state.records.filter(
    (record) =>
      record.rule.status === "active" &&
      record.rule.source !== "imported" &&
      !scopes.some((scope) => belongsToScope({ record, scope })),
  );

  if (unresolved.length) {
    console.log(
      `${unresolved.length} learning(s) remain stored for unregistered repository scopes; register their original repository with --repo to publish them.`,
    );
  }

  if (!apply) {
    console.log(
      "Preview only. --automatic authorizes supported skill edits; --memory enables recurring memory extraction. Native memory is never changed.",
    );

    return true;
  }

  if (memory) {
    const config = await readConfig();

    await writeConfig({
      config: setSourceEnabled({
        config,
        source: "claude-memory",
        enabled: true,
      }),
    });
  }

  if (activateOnly) {
    console.log(
      `Activated skill delivery in revision ${(await activateEnvironment(projectPaths)) ?? "unchanged"}.`,
    );

    return true;
  }

  const { config, policy } = await readEffectiveConfig();
  if (!policy.enabled || policy.distillation !== "allowed") throw new Error("Managed policy does not allow migration learning");
  const preferences = selectLearningPreferences({ explicit: { engine, model }, saved: config.distillation });
  const detection = await detectEngine({
    purpose: "distill",
    allowedEngines: policy.allowedEngines,
    preferredEngine: preferences.engine,
    model: preferences.model,
  });

  if (!detection.runner || !detection.selectedEngine) {
    throw new Error("No authenticated learning engine is available");
  }

  const detectedRunner = detection.runner;
  const execution = createLearningExecution({
    engine: detection.selectedEngine,
    runner: (run) =>
      detectedRunner({
        ...run,
        ...(preferences.model ? { model: preferences.model } : {}),
        reasoningEffort: "medium",
      }),
  });

  console.log(
    "Migration learning is limited to 20 calls, five minutes, and the engine's supported $2 ceiling.",
  );

  const summary = await updateLearningEnvironment({
    paths: projectPaths,
    execution,
  });

  console.log(JSON.stringify(summary));

  if (activate) {
    console.log(
      `Activated skill delivery in revision ${(await activateEnvironment(projectPaths)) ?? "unchanged"}.`,
    );
  } else {
    console.log(
      "Run migrate skills --apply --activate after all applicable learning is published. Remaining batches resume without replacing the original baseline.",
    );
  }

  return true;
}
