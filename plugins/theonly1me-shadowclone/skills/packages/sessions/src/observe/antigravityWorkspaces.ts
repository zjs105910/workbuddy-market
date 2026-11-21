import { stat } from "node:fs/promises";
import path from "node:path";
import { readBoundedFile, maximumTranscriptWindowBytes } from "@shadowclone/core";
import { isRecord, readString, readTimestamp } from "./record";

export type AntigravityWorkspaceBinding = {
  readonly sessionId: string;
  readonly timestamp: number;
  readonly workspace: string;
};

export type AntigravityWorkspaceRead = {
  readonly bindings: readonly AntigravityWorkspaceBinding[];
  readonly bytesRead: number;
  readonly invalidRecords: number;
};

export function parseAntigravityWorkspaceHistory(
  text: string,
): AntigravityWorkspaceRead {
  const bindings: AntigravityWorkspaceBinding[] = [];
  let invalidRecords = 0;

  for (const line of text.split("\n")) {
    if (line.trim().length === 0) {
      continue;
    }

    let value: unknown;

    try {
      value = JSON.parse(line);
    } catch {
      invalidRecords += 1;

      continue;
    }

    if (!isRecord(value)) {
      invalidRecords += 1;

      continue;
    }

    const sessionId = readString(value, "conversationId");
    const workspace = readString(value, "workspace");
    const timestamp = readTimestamp(value.timestamp);

    if (
      sessionId === null ||
      workspace === null ||
      !path.isAbsolute(workspace) ||
      timestamp <= 0
    ) {
      invalidRecords += 1;

      continue;
    }

    bindings.push({ sessionId, timestamp, workspace });
  }

  return {
    bindings: bindings.sort(
      (left, right) =>
        left.timestamp - right.timestamp ||
        left.sessionId.localeCompare(right.sessionId),
    ),
    bytesRead: Buffer.byteLength(text, "utf8"),
    invalidRecords,
  };
}

export async function readAntigravityWorkspaceHistory(
  sourcePath: string,
): Promise<AntigravityWorkspaceRead | null> {
  const size = await stat(sourcePath)
    .then((value) => value.size)
    .catch(() => 0);

  if (size < 1 || size > maximumTranscriptWindowBytes) {
    return null;
  }

  const text = await readBoundedFile({
    filePath: sourcePath,
    roots: [path.dirname(sourcePath)],
    maximumBytes: maximumTranscriptWindowBytes,
  });

  return text === null ? null : parseAntigravityWorkspaceHistory(text);
}
