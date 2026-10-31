import { openCursorDatabase, type FileStats } from "./cursorDatabase";
import {
  maximumTextBytes,
  maximumTranscriptWindowBytes,
} from "@shadowclone/core";
import type { Database } from "bun:sqlite";
import path from "node:path";
import { isRecord, readString, readTimestamp } from "../record";
import type { FileCursor } from "../types";

export type CursorBlob = {
  readonly id: string;
  readonly value: unknown;
};

export type CursorStore = {
  readonly blobs: readonly CursorBlob[];
  readonly sessionId: string;
  readonly cwd: string;
  readonly timestamp: number;
  readonly cursor: FileCursor;
  readonly bytesRead: number;
};

type BlobRow = {
  readonly id: string;
  readonly data: Uint8Array;
};

type MetaRow = {
  readonly value: string;
};

function decodeMeta(value: string): unknown {
  const text = /^(?:[0-9a-fA-F]{2})+$/.test(value)
    ? new TextDecoder().decode(
        Uint8Array.from(
          value.match(/.{2}/g)?.map((byte) => Number.parseInt(byte, 16)) ?? [],
        ),
      )
    : value;

  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function decodeBlob(data: Uint8Array): unknown {
  try {
    return JSON.parse(new TextDecoder().decode(data));
  } catch {
    return null;
  }
}

async function readSidecar(sourcePath: string): Promise<unknown> {
  const sidecar = Bun.file(path.join(path.dirname(sourcePath), "meta.json"));

  if (!(await sidecar.exists()) || sidecar.size > maximumTextBytes) {
    return null;
  }

  try {
    return JSON.parse(await sidecar.text());
  } catch {
    return null;
  }
}

export async function readCursorStore(options: {
  readonly sourcePath: string;
  readonly signature: FileStats;
}): Promise<CursorStore | null> {
  let database: Database | null = null;

  try {
    database = openCursorDatabase(options.sourcePath);

    const totalBytes =
      database
        .query<{ bytes: number }, []>(
          "SELECT coalesce(sum(length(data) + length(id) + 64), 0) AS bytes FROM blobs",
        )
        .get()?.bytes ?? 0;

    if (totalBytes > maximumTranscriptWindowBytes) {
      console.warn(
        "cursor: skipped a store exceeding the capture window limit",
      );

      return null;
    }

    const blobs = database
      .query<BlobRow, []>("SELECT id, data FROM blobs ORDER BY rowid")
      .all()
      .flatMap((row) => {
        const value = decodeBlob(row.data);

        return value === null ? [] : [{ id: row.id, value }];
      });

    const storedMeta = decodeMeta(
      database
        .query<MetaRow, []>(
          "SELECT value FROM meta WHERE key = '0' AND length(value) <= 1048576",
        )
        .get()?.value ?? "",
    );

    const sidecar = await readSidecar(options.sourcePath);
    const storedRecord = isRecord(storedMeta) ? storedMeta : {};
    const sidecarRecord = isRecord(sidecar) ? sidecar : {};

    return {
      blobs,
      sessionId:
        readString(storedRecord, "agentId") ??
        path.basename(path.dirname(options.sourcePath)),
      cwd: readString(sidecarRecord, "cwd") ?? "",
      timestamp:
        readTimestamp(sidecarRecord.createdAtMs) ||
        readTimestamp(storedRecord.createdAt) ||
        options.signature.modifiedAt,
      cursor: {
        sourcePath: options.sourcePath,
        byteSize: options.signature.size,
        modifiedAt: options.signature.modifiedAt,
        byteOffset: options.signature.size,
      },
      bytesRead: options.signature.size,
    };
  } catch {
    console.warn(
      `cursor: skipped an unreadable store (${options.signature.size} bytes)`,
    );

    return null;
  } finally {
    database?.close();
  }
}

export { cursorStoreSignature } from "./cursorDatabase";
