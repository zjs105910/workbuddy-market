import { isRecord, readString, readTimestamp } from "../record";
import type {
  AgentEvent,
  AgentEventKind,
  FileTextRef,
  ToolCall,
} from "../types";

const toolStepTypes = new Set([
  "CODE_ACTION",
  "GREP_SEARCH",
  "LIST_DIRECTORY",
  "MCP_TOOL",
  "REPLACE_FILE_CONTENT",
  "RUN_COMMAND",
  "VIEW_FILE",
  "WRITE_TO_FILE",
]);

function firstToolCall(
  record: Readonly<Record<string, unknown>>,
): ToolCall | null {
  const toolCalls = record.tool_calls;

  if (!Array.isArray(toolCalls)) {
    return null;
  }

  const toolCall = toolCalls.find(isRecord);

  if (!toolCall) {
    return null;
  }

  return {
    toolUseId:
      readString(toolCall, "id") ?? readString(toolCall, "tool_call_id"),
    name: readString(toolCall, "name") ?? "unknown",
  };
}

function toolResult(
  record: Readonly<Record<string, unknown>>,
  stepType: string,
): ToolCall {
  return {
    toolUseId:
      readString(record, "tool_call_id") ?? readString(record, "call_id"),
    name: readString(record, "tool_name") ?? stepType.toLowerCase(),
  };
}

function stepKind(
  record: Readonly<Record<string, unknown>>,
): AgentEventKind | null {
  const stepType = readString(record, "type");

  if (stepType === "USER_INPUT") {
    return readString(record, "content") === null ? null : "user-prompt";
  }

  if (stepType === "PLANNER_RESPONSE") {
    if (firstToolCall(record)) {
      return "tool-call";
    }

    if (record.thinking !== undefined) {
      return "thinking";
    }

    return readString(record, "content") === null
      ? "thinking"
      : "assistant-text";
  }

  if (stepType === "CHECKPOINT") {
    return "session-end";
  }

  return stepType !== null && toolStepTypes.has(stepType)
    ? "tool-result"
    : null;
}

export function parseStep(options: {
  readonly value: unknown;
  readonly ref: FileTextRef;
  readonly sessionId: string;
}): AgentEvent | null {
  if (!isRecord(options.value)) {
    return null;
  }

  const rawKind = stepKind(options.value);
  const stepType = readString(options.value, "type");

  if (rawKind === null || stepType === null) {
    return null;
  }

  const status = readString(options.value, "status");
  const kind = status === "CANCELED" ? "interruption" : rawKind;
  const stepIndex = options.value.step_index;

  const tool =
    rawKind === "tool-call"
      ? firstToolCall(options.value)
      : rawKind === "tool-result"
        ? toolResult(options.value, stepType)
        : null;

  return {
    source: "antigravity",
    sessionId: options.sessionId,
    eventId: `antigravity:${
      typeof stepIndex === "number" ? stepIndex : options.ref.byteOffset
    }`,
    parentEventId: null,
    timestamp: readTimestamp(options.value.created_at),
    cwd: readString(options.value, "workspace") ?? "",
    gitBranch: readString(options.value, "git_branch"),
    kind,
    tool,
    isError: status === "ERROR",
    textRef:
      kind === "user-prompt" || kind === "assistant-text" ? options.ref : null,
  };
}
