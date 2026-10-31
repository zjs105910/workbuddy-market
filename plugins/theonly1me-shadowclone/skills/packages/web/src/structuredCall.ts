import { z } from "zod";
import { createLearningExecution, type LearningExecutionLimits } from "@shadowclone/agents";
import { redactSecrets } from "@shadowclone/redact";
import type { GenerationEngine } from "./generationEngine";

export function generationDestination(connection: GenerationEngine): string {
  return `${connection.engine} using ${connection.model ?? "its default model"}`;
}

export async function structuredCall<Output>(options: {
  readonly connection: GenerationEngine;
  readonly prompt: string;
  readonly schema: z.ZodType<Output>;
  readonly limits: LearningExecutionLimits;
  readonly cwd: string;
  readonly signal: AbortSignal;
  readonly task: string;
}): Promise<Output> {
  const execution = createLearningExecution({
    engine: options.connection.engine,
    runner: (run) =>
      options.connection.runner({ ...run, signal: run.signal ? AbortSignal.any([run.signal, options.signal]) : options.signal }),
    limits: options.limits,
  });
  const destination = generationDestination(options.connection);
  const result = await execution
    .runner({
      prompt: options.prompt,
      cwd: options.cwd,
      execution: { purpose: "learning" },
      outputSchema: z.toJSONSchema(options.schema, { target: "draft-7" }),
    })
    .catch((error: unknown) => {
      const limitMessages: Readonly<Record<string, string>> = {
        "Learning deadline reached": `${destination} did not ${options.task} within ${options.limits.timeoutMilliseconds / 1000} seconds.`,
        "Learning cost limit reached": `${destination} reached the $${options.limits.maximumCostUsd} cost limit before it could ${options.task}.`,
      };
      const message = error instanceof Error ? limitMessages[error.message] : undefined;

      throw message ? new Error(message) : error;
    });

  options.signal.throwIfAborted();

  if (result.isError) {
    const reason = redactSecrets({ text: result.errorMessage ?? "No provider diagnostic was returned." }).slice(0, 600);

    throw new Error(`${destination} could not ${options.task}: ${reason}`);
  }

  return options.schema.parse(result.structured ?? JSON.parse(result.text));
}
