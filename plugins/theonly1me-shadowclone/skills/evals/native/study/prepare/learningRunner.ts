import { mkdir, mkdtemp, rm } from "node:fs/promises";
import path from "node:path";
import { runNativeEngine, type NativeEngineRunner } from "@shadowclone/agents";
import type { EngineRunner } from "@shadowclone/agents";
import { ownedWrite } from "@shadowclone/core";
import type { EvaluationBudget } from "../../../shared/accounting";

export function createLearningRunner(options: {
  readonly directory: string;
  readonly budget: EvaluationBudget;
  readonly blockedPaths: readonly string[];
  readonly cliVersion: string;
  readonly deadlineAt: number;
  readonly label: string;
  readonly nativeRunner?: NativeEngineRunner;
}): EngineRunner {
  const nativeRunner = options.nativeRunner ?? runNativeEngine;
  let calls = 0;

  return async (run) => {
    if (Date.now() >= options.deadlineAt) {
      throw new Error("Study preparation deadline reached");
    }

    await options.budget.reserve();
    calls += 1;
    const container = await mkdtemp(path.join(options.directory, "learning-call-"));
    const directory = path.join(container, "workspace");
    const homeDirectory = path.join(container, "home");
    await mkdir(directory, { mode: 0o700 });
    await mkdir(homeDirectory, { mode: 0o700 });
    let settled = false;

    try {
      const result = await nativeRunner({
        engine: "codex", directory, homeDirectory, access: "none", memoryEnabled: false,
        blockedPaths: options.blockedPaths, protectedPaths: [], prompt: run.prompt,
        outputSchema: run.outputSchema, signal: run.signal, expectedCliVersion: options.cliVersion,
      });
      await options.budget.settle(result.costUsd);
      settled = true;

      if (result.actions.length > 0) {
        throw new Error("Learning attempted a tool action");
      }

      await ownedWrite({
        path: path.join(options.directory, `${options.label}-learning-${calls}.json`),
        content: JSON.stringify({ resolvedModel: result.resolvedModel, isError: result.isError, durationMs: result.durationMs }),
      });
      return result;
    } finally {
      if (!settled) {
        await options.budget.settle(null);
      }

      await rm(container, { recursive: true, force: true });
    }
  };
}
