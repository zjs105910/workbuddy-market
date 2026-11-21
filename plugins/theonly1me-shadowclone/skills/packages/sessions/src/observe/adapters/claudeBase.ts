import path from "node:path";
import { readString, readTimestamp } from "../record";
import type { AgentEvent, FileTextRef } from "../types";

export function createClaudeBaseEvent(options: {
  readonly record: Readonly<Record<string, unknown>>;
  readonly message: Readonly<Record<string, unknown>>;
  readonly ref: FileTextRef;
}): Omit<AgentEvent, "kind" | "tool" | "isError" | "textRef"> {
  const fallbackId = `${path.basename(options.ref.sourcePath)}:${readTimestamp(options.record.timestamp)}`;

  return {
    source: "claude-code",
    sessionId:
      readString(options.record, "sessionId") ??
      path.basename(options.ref.sourcePath, ".jsonl"),
    eventId:
      readString(options.message, "id") ??
      readString(options.record, "uuid") ??
      fallbackId,
    parentEventId: readString(options.record, "parentUuid"),
    timestamp: readTimestamp(options.record.timestamp),
    cwd: readString(options.record, "cwd") ?? "",
    gitBranch: readString(options.record, "gitBranch"),
  };
}
