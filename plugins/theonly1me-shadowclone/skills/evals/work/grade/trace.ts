import { z } from "zod";

const blockSchema = z.looseObject({
  type: z.string(),
  text: z.string().optional(),
  name: z.string().optional(),
  input: z.unknown().optional(),
  content: z.unknown().optional(),
});

const lineSchema = z.looseObject({
  type: z.string().optional(),
  message: z
    .looseObject({ role: z.string().optional(), content: z.union([z.string(), z.array(blockSchema)]).optional() })
    .optional(),
});

export type TraceTurn = {
  readonly role: "user" | "assistant" | "tool_call" | "tool_result";
  readonly content: string;
  readonly name?: string;
};

function text(value: unknown): string {
  return typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

export function parseTrace(raw: string): readonly TraceTurn[] {
  return raw
    .split("\n")
    .filter((line) => line.trim().length > 0)
    .flatMap((line): readonly TraceTurn[] => {
      const parsed = lineSchema.safeParse(JSON.parse(line));

      if (!parsed.success || parsed.data.message === undefined) {
        return [];
      }

      const assistant = parsed.data.type === "assistant" || parsed.data.message.role === "assistant";
      const content = parsed.data.message.content;

      if (typeof content === "string") {
        return [{ role: assistant ? "assistant" : "user", content }];
      }

      return (content ?? []).flatMap((block): readonly TraceTurn[] => {
        if (block.type === "tool_use") {
          return [{ role: "tool_call", name: block.name ?? "tool", content: text(block.input) }];
        }

        if (block.type === "tool_result") {
          return [{ role: "tool_result", content: text(block.content) }];
        }

        if (block.type === "text" && block.text !== undefined) {
          return [{ role: assistant ? "assistant" : "user", content: block.text }];
        }

        return [];
      });
    });
}

const bashInputSchema = z.looseObject({ command: z.string() });

export function bashCommands(turns: readonly TraceTurn[]): readonly string[] {
  return turns.flatMap((turn) => {
    if (turn.role !== "tool_call" || turn.name !== "Bash") {
      return [];
    }

    const parsed = bashInputSchema.safeParse(JSON.parse(turn.content));

    return parsed.success ? [parsed.data.command] : [];
  });
}

export function finalMessage(turns: readonly TraceTurn[]): string {
  return [...turns].reverse().find((turn) => turn.role === "assistant")?.content ?? "";
}
