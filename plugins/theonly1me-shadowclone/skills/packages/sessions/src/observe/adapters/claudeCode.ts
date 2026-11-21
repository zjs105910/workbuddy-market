import { parseAssistant } from "./claudeAssistant";
import { existsSync } from "node:fs";
import path from "node:path";
import { readJsonLines } from "../cursor";
import {
  isRecord,
  readBoolean,
  readRecord,
  readString,
  readTimestamp,
} from "../record";
import type {
  AgentEvent,
  FileCursor,
  FileTextRef,
  ObservationBatch,
} from "../types";
import { parseClaudeUser } from "./claudeUser";

function parseClaudeRecord(options: {
  readonly value: unknown;
  readonly ref: FileTextRef;
}): readonly AgentEvent[] {
  if (!isRecord(options.value)) {
    return [];
  }

  const type = readString(options.value, "type");

  if (type === "result") {
    const timestamp = readTimestamp(options.value.timestamp);

    return [
      {
        source: "claude-code",
        sessionId:
          readString(options.value, "session_id") ??
          readString(options.value, "sessionId") ??
          path.basename(options.ref.sourcePath, ".jsonl"),
        eventId:
          readString(options.value, "uuid") ??
          `result:${path.basename(options.ref.sourcePath)}:${timestamp}`,
        parentEventId: readString(options.value, "parentUuid"),
        timestamp,
        cwd: readString(options.value, "cwd") ?? "",
        gitBranch: readString(options.value, "gitBranch"),
        kind: "session-end",
        tool: null,
        isError: readBoolean(options.value, "is_error"),
        textRef: null,
      },
    ];
  }

  const message = readRecord(options.value, "message");

  if (message === null) {
    return [];
  }

  if (type === "assistant") {
    return parseAssistant({ record: options.value, message, ref: options.ref });
  }

  if (type === "user") {
    return parseClaudeUser({
      record: options.value,
      message,
      ref: options.ref,
    });
  }

  return [];
}

export async function observeClaudeCodeFile(options: {
  readonly sourcePath: string;
  readonly cursor: FileCursor | null;
}): Promise<ObservationBatch | null> {
  const result = await readJsonLines(options);

  if (result === null) {
    return null;
  }

  return {
    source: "claude-code",
    sourcePath: options.sourcePath,
    events: result.values.flatMap(parseClaudeRecord),
    cursor: result.cursor,
    rescanned: result.rescanned,
    bytesRead: result.bytesRead,
    invalidRecords: result.invalidRecords,
  };
}

export async function discoverClaudeCodeFiles(
  projectsDirectory: string,
): Promise<readonly string[]> {
  if (!existsSync(projectsDirectory)) {
    return [];
  }

  const glob = new Bun.Glob("**/*.jsonl");
  const files: string[] = [];

  for await (const sourcePath of glob.scan({
    cwd: projectsDirectory,
    absolute: true,
    onlyFiles: true,
  })) {
    files.push(sourcePath);
  }

  return files.sort();
}
