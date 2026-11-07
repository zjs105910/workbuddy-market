import type { StudyAction } from "./record";

export type CommandOutput = { readonly command: string; readonly output: string };

function parse(line: string): Record<string, unknown> | null {
  try {
    const value: unknown = JSON.parse(line);
    return typeof value === "object" && value !== null && !Array.isArray(value) ? Object.fromEntries(Object.entries(value)) : null;
  } catch {
    return null;
  }
}

function blocks(record: Record<string, unknown>): Record<string, unknown>[] {
  const message = record.message;
  const content = typeof message === "object" && message !== null ? Reflect.get(message, "content") : null;
  return Array.isArray(content)
    ? content.flatMap((block) => typeof block === "object" && block !== null && !Array.isArray(block) ? [Object.fromEntries(Object.entries(block))] : [])
    : [];
}

function resultText(content: unknown): string {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content.map((part) => typeof part === "object" && part !== null && typeof Reflect.get(part, "text") === "string" ? String(Reflect.get(part, "text")) : "").join("\n");
}

export function commandOutputs(options: { engine: "codex" | "claude-code"; stream: string }): CommandOutput[] {
  const lines = options.stream.split("\n").flatMap((line) => { const record = parse(line); return record ? [record] : []; });

  if (options.engine === "codex") {
    return lines.flatMap((record) => {
      const item = record.item;
      if (record.type !== "item.completed" || typeof item !== "object" || item === null) return [];
      const command = Reflect.get(item, "command");
      const output = Reflect.get(item, "aggregated_output");
      return typeof command === "string" ? [{ command, output: typeof output === "string" ? output : "" }] : [];
    });
  }

  const commands = new Map<string, string>();
  const results = new Map<string, string>();
  const order: string[] = [];

  for (const record of lines) {
    for (const block of blocks(record)) {
      if (record.type === "assistant" && block.type === "tool_use" && block.name === "Bash" && typeof block.id === "string") {
        const input = block.input;
        const command = typeof input === "object" && input !== null ? Reflect.get(input, "command") : null;
        if (typeof command === "string") { commands.set(block.id, command); order.push(block.id); }
      }
      if (record.type === "user" && block.type === "tool_result" && typeof block.tool_use_id === "string") {
        results.set(block.tool_use_id, resultText(block.content));
      }
    }
  }

  return order.map((id) => ({ command: commands.get(id) ?? "", output: results.get(id) ?? "" }));
}

export function claudeFinalText(stream: string): string | null {
  for (const line of stream.split("\n").toReversed()) {
    const record = parse(line);
    if (record?.type === "result" && typeof record.result === "string") return record.result;
  }
  return null;
}

export function testRunResults(output: string): ("pass" | "fail")[] {
  const summaries = [...output.matchAll(/\b(\d+) pass\b[\s\S]{0,40}?\b(\d+) fail\b/g)].map((match): "pass" | "fail" => Number(match[2]) > 0 ? "fail" : "pass");
  if (summaries.length > 0) return summaries;
  if (/^\(fail\) /m.test(output)) return ["fail"];
  return /^\(pass\) /m.test(output) ? ["pass"] : [];
}

export function withTestRuns(options: {
  readonly actions: readonly StudyAction[];
  readonly outputs: readonly CommandOutput[];
}): StudyAction[] {
  const remaining = [...options.outputs];

  return options.actions.map((action) => {
    if (action.tool !== "Bash" || !action.command || !/\bbun\s+(?:run\s+)?test\b/.test(action.command)) return action;
    const position = remaining.findIndex((entry) => entry.command === action.command || action.command?.includes(entry.command) || entry.command.includes(action.command ?? ""));
    const found = position >= 0 ? remaining.splice(position, 1)[0] : undefined;
    const runs = found ? testRunResults(found.output) : [];
    return runs.length > 0 ? { ...action, testRuns: runs } : action;
  });
}
