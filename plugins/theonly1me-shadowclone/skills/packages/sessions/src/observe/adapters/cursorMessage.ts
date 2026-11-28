import { isRecord, readString } from "../record";
import type {
  AgentEvent,
  AgentEventKind,
  SqliteTextRef,
  ToolCall,
} from "../types";
import type { CursorBlob } from "./cursorStore";

type CursorContext = {
  readonly sourcePath: string;
  readonly sessionId: string;
  readonly cwd: string;
  readonly timestamp: number;
};

function textRef(options: {
  readonly context: CursorContext;
  readonly blobId: string;
  readonly jsonPath: readonly (string | number)[];
  readonly unwrap: SqliteTextRef["unwrap"];
}): SqliteTextRef {
  return {
    type: "sqlite-blob",
    sourcePath: options.context.sourcePath,
    blobId: options.blobId,
    jsonPath: options.jsonPath,
    unwrap: options.unwrap,
  };
}

function toolFromBlock(
  block: Readonly<Record<string, unknown>>,
): ToolCall | null {
  const type = readString(block, "type");

  if (type !== "tool-call" && type !== "tool_use" && type !== "tool_call") {
    return null;
  }

  return {
    toolUseId:
      readString(block, "toolCallId") ??
      readString(block, "tool_call_id") ??
      readString(block, "id"),
    name:
      readString(block, "toolName") ?? readString(block, "name") ?? "unknown",
  };
}

function event(options: {
  readonly context: CursorContext;
  readonly blobId: string;
  readonly index: number;
  readonly kind: AgentEventKind;
  readonly tool: ToolCall | null;
  readonly ref: SqliteTextRef | null;
}): AgentEvent {
  return {
    source: "cursor",
    sessionId: options.context.sessionId,
    eventId: `cursor:${options.blobId}:${options.index}`,
    parentEventId: null,
    timestamp: options.context.timestamp + options.index,
    cwd: options.context.cwd,
    gitBranch: null,
    kind: options.kind,
    tool: options.tool,
    isError: false,
    textRef: options.ref,
  };
}

function textEvent(options: {
  readonly context: CursorContext;
  readonly blobId: string;
  readonly index: number;
  readonly role: string;
  readonly text: string;
  readonly jsonPath: readonly (string | number)[];
}): AgentEvent | null {
  const userPrompt =
    options.role === "user" && options.text.includes("<user_query>");
  const assistantText = options.role === "assistant";

  if (!userPrompt && !assistantText) {
    return null;
  }

  return event({
    context: options.context,
    blobId: options.blobId,
    index: options.index,
    kind: userPrompt ? "user-prompt" : "assistant-text",
    tool: null,
    ref: textRef({
      context: options.context,
      blobId: options.blobId,
      jsonPath: options.jsonPath,
      unwrap: userPrompt ? "user-query" : null,
    }),
  });
}

export function parseCursorBlob(options: {
  readonly blob: CursorBlob;
  readonly context: CursorContext;
}): readonly AgentEvent[] {
  if (!isRecord(options.blob.value)) {
    return [];
  }

  const role = readString(options.blob.value, "role");

  if (role === "tool") {
    return [
      event({
        context: options.context,
        blobId: options.blob.id,
        index: 0,
        kind: "tool-result",
        tool: null,
        ref: null,
      }),
    ];
  }

  const content = options.blob.value.content;

  if (typeof content === "string") {
    const parsed = textEvent({
      context: options.context,
      blobId: options.blob.id,
      index: 0,
      role: role ?? "",
      text: content,
      jsonPath: ["content"],
    });

    return parsed ? [parsed] : [];
  }

  if (!Array.isArray(content)) {
    return [];
  }

  return content.flatMap((value, index) => {
    if (!isRecord(value)) {
      return [];
    }

    const type = readString(value, "type");

    if (role === "assistant" && type === "reasoning") {
      return [
        event({
          context: options.context,
          blobId: options.blob.id,
          index,
          kind: "thinking",
          tool: null,
          ref: null,
        }),
      ];
    }

    const tool = toolFromBlock(value);

    if (tool !== null) {
      return [
        event({
          context: options.context,
          blobId: options.blob.id,
          index,
          kind: "tool-call",
          tool,
          ref: null,
        }),
      ];
    }

    const text = readString(value, "text");

    const parsed = text
      ? textEvent({
          context: options.context,
          blobId: options.blob.id,
          index,
          role: role ?? "",
          text,
          jsonPath: ["content", index, "text"],
        })
      : null;

    return parsed ? [parsed] : [];
  });
}
