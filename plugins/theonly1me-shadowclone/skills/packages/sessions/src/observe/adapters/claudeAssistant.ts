import { isRecord, readString } from "../record";
import type {
  AgentEvent,
  AgentEventKind,
  FileTextRef,
  ToolCall,
} from "../types";
import { createClaudeBaseEvent } from "./claudeBase";

function classifyTool(name: string): AgentEventKind {
  if (name === "ExitPlanMode") {
    return "plan-presented";
  }

  if (name === "AskUserQuestion") {
    return "question-asked";
  }

  return "tool-call";
}

function getTool(block: Readonly<Record<string, unknown>>): ToolCall | null {
  if (readString(block, "type") !== "tool_use") {
    return null;
  }

  const name = readString(block, "name");

  if (name === null) {
    return null;
  }

  return {
    toolUseId: readString(block, "id"),
    name,
  };
}

function getContentBlocks(
  message: Readonly<Record<string, unknown>>,
): readonly unknown[] {
  const content = message.content;

  return Array.isArray(content) ? content : [content];
}

function getTextRef(options: {
  readonly blocks: readonly unknown[];
  readonly block: Readonly<Record<string, unknown>>;
  readonly ref: FileTextRef;
  readonly kind: AgentEventKind;
}): FileTextRef | null {
  return options.blocks.length === 1 &&
    (readString(options.block, "type") === "text" ||
      options.kind === "question-asked" ||
      options.kind === "plan-presented")
    ? options.ref
    : null;
}

export function parseAssistant(options: {
  readonly record: Readonly<Record<string, unknown>>;
  readonly message: Readonly<Record<string, unknown>>;
  readonly ref: FileTextRef;
}): readonly AgentEvent[] {
  const base = createClaudeBaseEvent(options);
  const blocks = getContentBlocks(options.message);
  const events: AgentEvent[] = [];

  for (const value of blocks) {
    if (!isRecord(value)) {
      continue;
    }

    const blockType = readString(value, "type");
    const tool = getTool(value);

    const kind =
      tool === null
        ? blockType === "thinking"
          ? "thinking"
          : "assistant-text"
        : classifyTool(tool.name);

    events.push({
      ...base,
      kind,
      tool,
      isError: false,
      textRef: getTextRef({
        blocks,
        block: value,
        ref: options.ref,
        kind,
      }),
    });
  }

  return events;
}
