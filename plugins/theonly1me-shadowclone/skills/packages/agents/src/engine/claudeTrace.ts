import { z } from "zod";
import type { EngineAction } from "./types";

const recordSchema = z.record(z.string(), z.unknown());

export function claudeTrace(stream: string): {
  readonly actions: readonly EngineAction[];
  readonly resolvedModel: string | null;
} {
  const requests: { id: string; action: EngineAction }[] = [];
  const results = new Map<
    string,
    { succeeded: boolean; resultSequence: number }
  >();
  const models = new Set<string>();
  let sequence = 0;

  for (const line of stream.split("\n")) {
    let value: unknown;

    try {
      value = JSON.parse(line);
    } catch {
      continue;
    }

    const parsed = recordSchema.safeParse(value);

    if (!parsed.success) {
      continue;
    }

    const record = parsed.data;

    if (
      record.type === "system" &&
      record.subtype === "init" &&
      typeof record.model === "string"
    ) {
      models.add(record.model);
    }

    const message = recordSchema.safeParse(record.message);

    if (!message.success || !Array.isArray(message.data.content)) {
      continue;
    }

    for (const value of message.data.content) {
      sequence += 1;

      const parsedBlock = recordSchema.safeParse(value);

      if (!parsedBlock.success) {
        continue;
      }

      const block = parsedBlock.data;

      if (
        record.type === "user" &&
        block.type === "tool_result" &&
        typeof block.tool_use_id === "string"
      ) {
        results.set(block.tool_use_id, {
          succeeded: block.is_error !== true,
          resultSequence: sequence,
        });
      }

      if (
        record.type !== "assistant" ||
        block.type !== "tool_use" ||
        typeof block.name !== "string"
      ) {
        continue;
      }

      const input = recordSchema.safeParse(block.input);
      const fields = input.success ? input.data : {};
      const rawPath = fields.file_path ?? fields.path ?? fields.notebook_path;

      requests.push({
        id: typeof block.id === "string" ? block.id : "",
        action: {
          tool: block.name,
          path: typeof rawPath === "string" ? rawPath : null,
          command: typeof fields.command === "string" ? fields.command : typeof fields.skill === "string" ? fields.skill : null,
          requestSequence: sequence,
        },
      });
    }
  }

  const [model] = models;

  return {
    resolvedModel: models.size === 1 ? (model ?? null) : null,
    actions: requests.map(({ id, action }) => ({
      ...action,
      succeeded: results.get(id)?.succeeded ?? null,
      resultSequence: results.get(id)?.resultSequence ?? null,
    })),
  };
}
