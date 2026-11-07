import path from "node:path";
import { maximumTextBytes } from "@shadowclone/core";
import type { SourceId } from "@shadowclone/core";

export type FileTextRef = {
  readonly contentHash?: string;
  readonly fileIdentity?: string;
  readonly type: "file";
  readonly sourcePath: string;
  readonly byteOffset: number;
  readonly byteLength: number;
};

export type SqliteTextRef = {
  readonly type: "sqlite-blob";
  readonly sourcePath: string;
  readonly blobId: string;
  readonly jsonPath: readonly (string | number)[];
  readonly unwrap: "user-query" | null;
};

export type TextRef = FileTextRef | SqliteTextRef;

function isRecord(value: unknown): value is Readonly<Record<string, unknown>> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function parseTextRef(value: unknown): TextRef | null {
  if (
    !isRecord(value) ||
    typeof value.sourcePath !== "string" ||
    !path.isAbsolute(value.sourcePath)
  ) {
    return null;
  }

  if (
    value.type === "file" &&
    typeof value.byteOffset === "number" &&
    typeof value.byteLength === "number" &&
    Number.isSafeInteger(value.byteOffset) &&
    value.byteOffset >= 0 &&
    Number.isSafeInteger(value.byteLength) &&
    value.byteLength > 0 &&
    value.byteLength <= maximumTextBytes &&
    Number.isSafeInteger(value.byteOffset + value.byteLength) &&
    (value.contentHash === undefined ||
      (typeof value.contentHash === "string" &&
        /^[a-f0-9]{64}$/.test(value.contentHash))) &&
    (value.fileIdentity === undefined || typeof value.fileIdentity === "string")
  ) {
    return {
      type: "file",
      sourcePath: value.sourcePath,
      byteOffset: value.byteOffset,
      byteLength: value.byteLength,
      ...(typeof value.contentHash === "string"
        ? { contentHash: value.contentHash }
        : {}),
      ...(typeof value.fileIdentity === "string"
        ? { fileIdentity: value.fileIdentity }
        : {}),
    };
  }

  if (
    value.type !== "sqlite-blob" ||
    typeof value.blobId !== "string" ||
    !Array.isArray(value.jsonPath) ||
    value.jsonPath.length > 32 ||
    value.blobId.length > 512 ||
    !value.jsonPath.every(
      (part) =>
        typeof part === "string" ||
        (typeof part === "number" && Number.isSafeInteger(part) && part >= 0),
    ) ||
    (value.unwrap !== null && value.unwrap !== "user-query")
  ) {
    return null;
  }

  return {
    type: "sqlite-blob",
    sourcePath: value.sourcePath,
    blobId: value.blobId,
    jsonPath: value.jsonPath,
    unwrap: value.unwrap,
  };
}

export function textRefKey(ref: TextRef): string {
  return JSON.stringify(ref);
}

export type FileCursor = {
  readonly identity?: string;
  readonly discarding?: boolean;
  readonly omittedRecords?: number;
  readonly sourcePath: string;
  readonly byteSize: number;
  readonly modifiedAt: number;
  readonly byteOffset: number;
};

export type ToolCall = {
  readonly toolUseId: string | null;
  readonly name: string;
};

export type AgentEventKind =
  | "user-prompt"
  | "assistant-text"
  | "thinking"
  | "tool-call"
  | "tool-result"
  | "plan-presented"
  | "plan-resolved"
  | "question-asked"
  | "question-answered"
  | "permission-denied"
  | "interruption"
  | "session-end";

export type AgentEvent = {
  readonly source: SourceId;
  readonly sessionId: string;
  readonly eventId: string;
  readonly parentEventId: string | null;
  readonly timestamp: number;
  readonly cwd: string;
  readonly gitBranch: string | null;
  readonly kind: AgentEventKind;
  readonly tool: ToolCall | null;
  readonly isError: boolean;
  readonly textRef: TextRef | null;
};

export type ObservationBatch = {
  readonly source: SourceId;
  readonly sourcePath: string;
  readonly events: readonly AgentEvent[];
  readonly cursor: FileCursor;
  readonly rescanned: boolean;
  readonly bytesRead: number;
  readonly invalidRecords: number;
};

export type CursorLookup = (
  sourcePath: string,
) => FileCursor | null | Promise<FileCursor | null>;
