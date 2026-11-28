import { mkdir, mkdtemp, rm } from "node:fs/promises";
import path from "node:path";
import { runNativeEngine, type NativeEngineRunner } from "@shadowclone/agents";
import type { EngineRunner } from "@shadowclone/agents";
import { ownedWrite } from "@shadowclone/core";
import { redactSecrets } from "@shadowclone/redact";
import type { EvaluationBudget } from "../../shared/accounting";
import type { LearnerConfiguration, LearningCall } from "./schema";

export function workflowLearningRunner(options: {
  directory: string;
  budget: EvaluationBudget;
  configuration: LearnerConfiguration;
  blockedPaths: string[];
  calls: LearningCall[];
  runner?: NativeEngineRunner;
}): EngineRunner {
  const nativeRunner = options.runner ?? runNativeEngine;
  const deadlineAt = Date.now() + options.configuration.deadlineSeconds * 1000;
  return async (run) => {
    const remaining = deadlineAt - Date.now();
    if (remaining <= 0) throw new Error("Learning preparation deadline reached");
    await options.budget.reserve();
    const startedAt = Date.now();
    const container = await mkdtemp(path.join(options.directory, "call-"));
    let costUsd: number | null = null;
    const call: LearningCall = {
      model: "unconfirmed",
      cliVersion: "unconfirmed",
      durationMs: 0,
      isError: true,
    };
    const callId = path.basename(container);
    try {
      const directory = path.join(container, "workspace");
      const homeDirectory = path.join(container, "home");
      await mkdir(directory, { mode: 0o700 });
      await mkdir(homeDirectory, { mode: 0o700 });
      const timeout = AbortSignal.timeout(
        Math.min(remaining, options.configuration.callSeconds * 1000),
      );
      const result = await nativeRunner({
        engine: options.configuration.engine,
        model: options.configuration.model,
        effort: options.configuration.effort,
        directory,
        homeDirectory,
        access: "none",
        memoryEnabled: false,
        blockedPaths: options.blockedPaths,
        protectedPaths: [],
        prompt: run.prompt,
        outputSchema: run.outputSchema,
        signal: run.signal ? AbortSignal.any([run.signal, timeout]) : timeout,
        expectedCliVersion: options.configuration.cliVersion,
        debugTransport: async (output) => {
          await ownedWrite({
            path: path.join(options.directory, `${callId}-transport.json`),
            content: JSON.stringify(output),
          });
        },
      });
      costUsd = result.costUsd;
      call.model = result.resolvedModel ?? "unconfirmed";
      call.cliVersion = result.cliVersion;
      if (
        result.isError ||
        result.actions.length > 0 ||
        result.resolvedModel !== options.configuration.model ||
        result.cliVersion !== options.configuration.cliVersion
      ) {
        throw new Error(
          "Learning failed, attempted a tool action, or did not confirm the pinned model and CLI",
        );
      }
      call.isError = false;
      return result;
    } catch (error) {
      await ownedWrite({
        path: path.join(options.directory, `${callId}-diagnostic.json`),
        content: JSON.stringify({
          stage: "learning-execution",
          message: redactSecrets({ text: error instanceof Error ? error.message : String(error) }),
          confirmedInfrastructure: false,
          model: call.model,
          cliVersion: call.cliVersion,
        }),
      });
      throw error;
    } finally {
      call.durationMs = Date.now() - startedAt;
      options.calls.push(call);
      await options.budget.settle(costUsd);
      await ownedWrite({
        path: path.join(options.directory, "calls.json"),
        content: JSON.stringify(options.calls, null, 2),
      });
      await rm(container, { recursive: true, force: true });
    }
  };
}
