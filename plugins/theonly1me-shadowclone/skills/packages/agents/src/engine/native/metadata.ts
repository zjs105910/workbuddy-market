import path from "node:path";
import { existsSync } from "node:fs";
import { z } from "zod";
import type { NativeEngineRun } from "./types";

const metadataSchema = z.object({
  type: z.string(),
  model: z.string().optional(),
  payload: z.object({ model: z.string().optional() }).optional(),
  usage: z.object({
    input_tokens: z.number().nonnegative().optional(),
    cached_input_tokens: z.number().nonnegative().optional(),
    cache_read_input_tokens: z.number().nonnegative().optional(),
    output_tokens: z.number().nonnegative().optional(),
  }).optional(),
});

function readMetadata(text: string) {
  return text.split("\n").flatMap((line) => {
    try {
      const parsed = metadataSchema.safeParse(JSON.parse(line));

      return parsed.success ? [parsed.data] : [];
    } catch {
      return [];
    }
  });
}

export async function nativeMetadata(options: {
  readonly stream: string;
  readonly homeDirectory: string;
  readonly sessionId: string;
}): Promise<{
  readonly resolvedModel: string | null;
  readonly usage: NativeEngineRun["usage"];
}> {
  const events = readMetadata(options.stream);
  const directory = path.join(options.homeDirectory, ".codex", "sessions");

  const files = existsSync(directory) ? new Bun.Glob("**/*.jsonl").scan({
    cwd: directory,
    onlyFiles: true,
    followSymlinks: false,
  }) : [];

  for await (const relative of files) {
    if (!relative.includes(options.sessionId)) {
      continue;
    }

    const file = Bun.file(path.join(directory, relative));

    if (file.size > 32_000_000) {
      throw new Error("Native metadata exceeds its evidence limit");
    }

    events.push(...readMetadata(await file.text()));
  }

  const models = new Set(events.flatMap((event) => {
    const model = event.type === "turn_context" ? event.payload?.model : event.model;

    return model ? [model] : [];
  }));
  const usage = events.filter((event) => event.usage).at(-1)?.usage;

  return {
    resolvedModel: models.size === 1 ? ([...models][0] ?? null) : null,
    usage: usage ? {
      inputTokens: usage.input_tokens ?? 0,
      cachedInputTokens: usage.cached_input_tokens ?? usage.cache_read_input_tokens ?? 0,
      outputTokens: usage.output_tokens ?? 0,
    } : null,
  };
}
