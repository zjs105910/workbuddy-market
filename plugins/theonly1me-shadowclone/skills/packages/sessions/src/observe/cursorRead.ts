import { constants } from "node:fs";
import { open } from "node:fs/promises";
import {
  maximumTranscriptRecordBytes,
  maximumTranscriptWindowBytes,
} from "@shadowclone/core";
import type { FileCursor, FileTextRef } from "./types";

type LineBoundaries = {
  readonly ref: FileTextRef;
  readonly bytes: Uint8Array;
};

export type CursorRead<Value> = {
  readonly values: readonly Value[];
  readonly cursor: FileCursor;
  readonly rescanned: boolean;
  readonly bytesRead: number;
  readonly invalidRecords: number;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isMissingFile(error: unknown): boolean {
  return isRecord(error) && error.code === "ENOENT";
}

export async function getLineBoundaries(options: {
  readonly sourcePath: string;
  readonly cursor: FileCursor | null;
}): Promise<CursorRead<LineBoundaries> | null> {
  const handle = await open(
    options.sourcePath,
    constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK,
  ).catch((error: unknown) => {
    if (isMissingFile(error)) {
      return null;
    }

    throw error;
  });

  if (handle === null) {
    return null;
  }

  try {
    const fileStats = await handle.stat();

    if (!fileStats.isFile()) {
      return null;
    }

    const modifiedAt = fileStats.mtimeMs;
    const identity = `${fileStats.dev}:${fileStats.ino}`;
    const previous = options.cursor;

    const rescanned =
      previous !== null &&
      ((previous.identity !== undefined && previous.identity !== identity) ||
        fileStats.size < previous.byteSize ||
        (fileStats.size === previous.byteSize &&
          modifiedAt !== previous.modifiedAt));

    const startOffset =
      previous === null || rescanned ? 0 : previous.byteOffset;
    const windowSize = Math.min(
      maximumTranscriptWindowBytes,
      Math.max(0, fileStats.size - startOffset),
    );
    const buffer = Buffer.alloc(windowSize);
    const read = await handle.read(buffer, 0, windowSize, startOffset);
    const bytes = buffer.subarray(0, read.bytesRead);
    const values: LineBoundaries[] = [];
    let lineStart = 0;
    let completedByteCount = 0;
    let discarding = !rescanned && (previous?.discarding ?? false);
    let omittedRecords = rescanned ? 0 : (previous?.omittedRecords ?? 0);

    for (let byteIndex = 0; byteIndex < bytes.length; byteIndex += 1) {
      if (bytes[byteIndex] !== 10) {
        continue;
      }

      const lineEnd =
        byteIndex > lineStart && bytes[byteIndex - 1] === 13
          ? byteIndex - 1
          : byteIndex;
      const byteLength = lineEnd - lineStart;

      if (!discarding && byteLength > maximumTranscriptRecordBytes) {
        omittedRecords += 1;
      } else if (!discarding && byteLength > 0) {
        values.push({
          ref: {
            type: "file",
            sourcePath: options.sourcePath,
            byteOffset: startOffset + lineStart,
            byteLength,
            fileIdentity: identity,
            contentHash: new Bun.CryptoHasher("sha256")
              .update(bytes.subarray(lineStart, lineEnd))
              .digest("hex"),
          },
          bytes: bytes.subarray(lineStart, lineEnd),
        });
      }

      discarding = false;
      lineStart = byteIndex + 1;
      completedByteCount = lineStart;
    }

    if (discarding || bytes.length - lineStart > maximumTranscriptRecordBytes) {
      if (!discarding) {
        omittedRecords += 1;
      }

      discarding = true;
      completedByteCount = bytes.length;
    }

    const after = await handle.stat();

    if (
      after.ino !== fileStats.ino ||
      after.size < fileStats.size ||
      (after.size === fileStats.size && after.mtimeMs !== modifiedAt)
    ) {
      throw new Error("Transcript changed while being read; retry observation");
    }

    return {
      values,
      cursor: {
        sourcePath: options.sourcePath,
        byteSize: fileStats.size,
        modifiedAt,
        byteOffset: startOffset + completedByteCount,
        identity,
        discarding,
        omittedRecords,
      },
      rescanned,
      bytesRead: bytes.length,
      invalidRecords:
        omittedRecords - (rescanned ? 0 : (previous?.omittedRecords ?? 0)),
    };
  } finally {
    await handle.close();
  }
}
