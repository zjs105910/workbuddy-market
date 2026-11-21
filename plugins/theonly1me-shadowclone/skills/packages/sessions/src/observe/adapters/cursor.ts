import type { AgentEvent, FileCursor, ObservationBatch } from "../types";
import { parseCursorBlob } from "./cursorMessage";
import { cursorStoreSignature, readCursorStore } from "./cursorStore";

export async function observeCursorFile(options: {
  readonly sourcePath: string;
  readonly cursor: FileCursor | null;
}): Promise<ObservationBatch | null> {
  const signature = await cursorStoreSignature(options.sourcePath);

  if (signature === null) {
    return null;
  }

  if (
    options.cursor !== null &&
    options.cursor.byteSize === signature.size &&
    options.cursor.modifiedAt === signature.modifiedAt
  ) {
    return {
      source: "cursor",
      sourcePath: options.sourcePath,
      events: [],
      cursor: options.cursor,
      rescanned: false,
      bytesRead: 0,
      invalidRecords: 0,
    };
  }

  const store = await readCursorStore({
    sourcePath: options.sourcePath,
    signature,
  });

  if (store === null) {
    return null;
  }

  const events: AgentEvent[] = [];
  let parentEventId: string | null = null;

  for (const blob of store.blobs) {
    for (const parsed of parseCursorBlob({
      blob,
      context: {
        sourcePath: options.sourcePath,
        sessionId: store.sessionId,
        cwd: store.cwd,
        timestamp: store.timestamp + events.length,
      },
    })) {
      const event: AgentEvent = { ...parsed, parentEventId };

      events.push(event);
      parentEventId = event.eventId;
    }
  }

  return {
    source: "cursor",
    sourcePath: options.sourcePath,
    events,
    cursor: store.cursor,
    rescanned: options.cursor !== null,
    bytesRead: store.bytesRead,
    invalidRecords: 0,
  };
}

export async function discoverCursorFiles(
  chatsDirectory: string,
): Promise<readonly string[]> {
  const files: string[] = [];

  for await (const sourcePath of new Bun.Glob("**/store.db").scan({
    cwd: chatsDirectory,
    absolute: true,
    onlyFiles: true,
  })) {
    files.push(sourcePath);
  }

  return files.sort();
}
