import { z } from "zod";
import { createLearningExecution } from "@shadowclone/agents";
import { fingerprint } from "@shadowclone/core";
import { redactSecrets } from "@shadowclone/redact";
import {
  allowedGenerationEngines,
  generationEngine,
  generationLimits,
  type GenerationEngine,
} from "./generationEngine";
import type { BuildContext } from "@shadowclone/environment";

export function createReviewedGeneration<Output>(options: {
  readonly context: BuildContext & { readonly engine?: GenerationEngine };
  readonly prompt: (input: unknown) => Promise<string>;
  readonly schema: z.ZodType<Output>;
}) {
  const reviews = new Map<
    string,
    GenerationEngine & {
      readonly input: unknown;
      readonly payload: string;
      readonly key: string;
    }
  >();

  const cache = new Map<string, Output>();
  let running = false;

  return {
    async preview(input: unknown) {
      if (running)
        throw new Error("Wait for the current model request to finish");

      const payload = await options.prompt(input);

      if (Buffer.byteLength(payload) > 28_000) {
        throw new Error(
          "The model request is too large; shorten the instructions",
        );
      }

      const connection = await generationEngine(options.context);
      const key = fingerprint(JSON.stringify({ engine: connection.engine, model: connection.model ?? null, payload }));
      const id = crypto.randomUUID();

      reviews.clear();
      reviews.set(id, { ...connection, input, payload, key });

      return {
        id,
        destination: `${connection.engine} using ${connection.model ?? "its default model"}`,
        payload,
        limits: generationLimits(connection.engine),
        cached: cache.get(key) ?? null,
      };
    },

    async generate(request: {
      readonly id: string;
      readonly signal?: AbortSignal;
    }): Promise<Output> {
      const review = reviews.get(request.id);

      if (!review || running) {
        throw new Error("Review a fresh model request before generating");
      }

      running = true;
      reviews.delete(request.id);

      try {
        const allowed = await allowedGenerationEngines(options.context);
        const current = await options.prompt(review.input);

        if (!allowed.includes(review.engine) || current !== review.payload) {
          throw new Error(
            "The input or permissions changed; review a fresh model request",
          );
        }

        const cached = cache.get(review.key);

        if (cached !== undefined) return cached;

        request.signal?.throwIfAborted();

        const execution = createLearningExecution({
          engine: review.engine,
          runner: (run) =>
            review.runner({
              ...run,
              signal: AbortSignal.any(
                [run.signal, request.signal].filter(
                  (signal): signal is AbortSignal => signal !== undefined,
                ),
              ),
            }),
          limits: {
            maximumCalls: 1,
            timeoutMilliseconds: 60_000,
            maximumCostUsd: 0.25,
          },
        });

        const result = await execution.runner({
          prompt: review.payload,
          cwd: options.context.cwd,
          execution: { purpose: "learning" },
          outputSchema: z.toJSONSchema(options.schema, { target: "draft-7" }),
        });

        request.signal?.throwIfAborted();

        if (result.isError) {
          const reason = redactSecrets({
            text: result.errorMessage ?? "No provider diagnostic was returned.",
          }).slice(0, 1200);

          throw new Error(
            `${review.engine} could not complete the request: ${reason} Your draft is unchanged.`,
          );
        }

        const output = options.schema.parse(
          result.structured ?? JSON.parse(result.text),
        );

        if (cache.size >= 32) cache.clear();

        cache.set(review.key, output);

        return output;
      } finally {
        running = false;
      }
    },
  };
}
