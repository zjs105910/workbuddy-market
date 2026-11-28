import { parseStep } from "./antigravityStep";
import { stat } from "node:fs/promises";
import path from "node:path";
import { readJsonLines } from "../cursor";
import { isRecord } from "../record";
import type { FileCursor, ObservationBatch } from "../types";

function sessionIdFromPath(sourcePath: string): string {
  return path.basename(path.dirname(path.dirname(path.dirname(sourcePath))));
}

export async function observeAntigravityFile(options: {
  readonly sourcePath: string;
  readonly cursor: FileCursor | null;
}): Promise<ObservationBatch | null> {
  const result = await readJsonLines(options);

  if (result === null) {
    return null;
  }

  const sessionId = sessionIdFromPath(options.sourcePath);
  let parentEventId: string | null = null;

  const events = result.values.flatMap((line) => {
    const event = parseStep({ ...line, sessionId });

    if (event === null) {
      return [];
    }

    const chained = { ...event, parentEventId };

    parentEventId = event.eventId;

    return [chained];
  });

  return {
    source: "antigravity",
    sourcePath: options.sourcePath,
    events,
    cursor: result.cursor,
    rescanned: result.rescanned,
    bytesRead: result.bytesRead,
    invalidRecords: result.invalidRecords,
  };
}

export async function discoverAntigravityFiles(
  brainDirectory: string,
): Promise<readonly string[]> {
  try {
    if (!(await stat(brainDirectory)).isDirectory()) {
      return [];
    }
  } catch (error) {
    if (isRecord(error) && error.code === "ENOENT") {
      return [];
    }

    throw error;
  }

  const files: string[] = [];
  const transcriptPattern = "*/.system_generated/logs/transcript_full.jsonl";

  for await (const sourcePath of new Bun.Glob(transcriptPattern).scan({
    cwd: brainDirectory,
    absolute: true,
    dot: true,
    onlyFiles: true,
  })) {
    files.push(sourcePath);
  }

  return files.sort();
}
