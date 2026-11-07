import { constants } from "node:fs";
import { open, lstat } from "node:fs/promises";
import { readJsonLines, type JsonLine } from "../cursor";
import { isRecord } from "../record";
import type { AgentEvent, FileCursor, ObservationBatch } from "../types";

async function sessionHeader(sourcePath: string): Promise<Readonly<Record<string, unknown>> | null> {
  const file = await open(sourcePath, constants.O_RDONLY | constants.O_NOFOLLOW);
  try {
    const buffer = Buffer.alloc(65536);
    const result = await file.read(buffer, 0, buffer.length, 0);
    const newline = buffer.subarray(0, result.bytesRead).indexOf(10);
    if (newline < 0) return null;
    const value: unknown = JSON.parse(buffer.subarray(0, newline).toString("utf8"));
    return isRecord(value) && value.type === "session" && typeof value.id === "string" &&
      typeof value.cwd === "string" && value.version === 3 ? value : null;
  } catch { return null; }
  finally { await file.close(); }
}

function piEvent(options: {
  readonly line: JsonLine;
  readonly sessionId: string;
  readonly cwd: string;
}): AgentEvent | null {
  const value = options.line.value;
  if (!isRecord(value) || typeof value.id !== "string" || value.type === "session") return null;
  const timestamp = typeof value.timestamp === "string" ? Date.parse(value.timestamp) : NaN;
  if (!Number.isFinite(timestamp)) return null;
  const message = isRecord(value.message) ? value.message : null;
  const role = value.type === "message" ? message?.role : null;
  const eligible = role === "user" || role === "assistant";
  const text = message?.content;
  const hasText = typeof text === "string" || (Array.isArray(text) && text.some(block =>
    isRecord(block) && block.type === "text" && typeof block.text === "string"));
  return {
    source: "pi", sessionId: options.sessionId,
    eventId: `${options.sessionId}:${value.id}`,
    parentEventId: typeof value.parentId === "string" ? `${options.sessionId}:${value.parentId}` : null,
    timestamp, cwd: options.cwd, gitBranch: null,
    kind: role === "user" ? "user-prompt" : role === "assistant" ? "assistant-text" : "tool-result",
    tool: null, isError: message?.stopReason === "error" || message?.stopReason === "aborted",
    textRef: eligible && hasText ? options.line.ref : null,
  };
}

export async function observePiFile(options: {
  readonly sourcePath: string;
  readonly cursor: FileCursor | null;
}): Promise<ObservationBatch | null> {
  const metadata = await lstat(options.sourcePath).catch(() => null);
  if (!metadata?.isFile() || metadata.isSymbolicLink()) return null;
  const result = await readJsonLines(options);
  if (!result) return null;
  const header = await sessionHeader(options.sourcePath);
  const events = header && typeof header.id === "string" && typeof header.cwd === "string"
    ? result.values.flatMap(line => {
        const event = piEvent({ line, sessionId: String(header.id), cwd: String(header.cwd) });
        return event ? [event] : [];
      }) : [];
  return {
    source: "pi", sourcePath: options.sourcePath, events,
    cursor: result.cursor, rescanned: result.rescanned, bytesRead: result.bytesRead,
    invalidRecords: result.invalidRecords + (header ? 0 : 1),
  };
}

export async function discoverPiFiles(directory: string): Promise<readonly string[]> {
  const metadata = await lstat(directory).catch(() => null);
  if (!metadata?.isDirectory() || metadata.isSymbolicLink()) return [];
  const files: string[] = [];
  for await (const file of new Bun.Glob("**/*.jsonl").scan({ cwd: directory, absolute: true, onlyFiles: true, followSymlinks: false })) {
    files.push(file);
  }
  return files.sort();
}
