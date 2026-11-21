import path from "node:path";
import { readJsonLines } from "../cursor";
import { isRecord, readString, readTimestamp } from "../record";
import type {
  AgentEvent,
  FileCursor,
  FileTextRef,
  ObservationBatch,
} from "../types";

function parsePrompt(options: {
  readonly value: unknown;
  readonly ref: FileTextRef;
}): AgentEvent | null {
  if (!isRecord(options.value)) {
    return null;
  }

  const prompt =
    readString(options.value, "display") ?? readString(options.value, "prompt");

  if (prompt === null) {
    return null;
  }

  const timestamp = readTimestamp(options.value.timestamp);

  return {
    source: "claude-prompts",
    sessionId: readString(options.value, "sessionId") ?? "claude-prompts",
    eventId:
      readString(options.value, "id") ??
      `prompt:${timestamp}:${options.ref.byteOffset}`,
    parentEventId: null,
    timestamp,
    cwd: readString(options.value, "project") ?? "",
    gitBranch: null,
    kind: "user-prompt",
    tool: null,
    isError: false,
    textRef: options.ref,
  };
}

export async function observeClaudePromptsFile(options: {
  readonly sourcePath: string;
  readonly cursor: FileCursor | null;
}): Promise<ObservationBatch | null> {
  const result = await readJsonLines(options);

  if (result === null) {
    return null;
  }

  const events = result.values
    .map(parsePrompt)
    .filter((event): event is AgentEvent => event !== null);

  return {
    source: "claude-prompts",
    sourcePath: path.resolve(options.sourcePath),
    events,
    cursor: result.cursor,
    rescanned: result.rescanned,
    bytesRead: result.bytesRead,
    invalidRecords: result.invalidRecords,
  };
}
