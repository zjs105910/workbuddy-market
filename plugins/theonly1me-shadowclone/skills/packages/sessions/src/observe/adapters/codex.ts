import { parseRecord } from "./codexRecord";
import { existsSync } from "node:fs";
import { readJsonLines } from "../cursor";
import type { FileCursor, ObservationBatch } from "../types";
import { getCodexContext } from "./codexContext";

export async function observeCodexFile(options: {
  readonly sourcePath: string;
  readonly cursor: FileCursor | null;
}): Promise<ObservationBatch | null> {
  const result = await readJsonLines(options);

  if (result === null) {
    return null;
  }

  if (result.values.length === 0) {
    return {
      source: "codex",
      sourcePath: options.sourcePath,
      events: [],
      cursor: result.cursor,
      rescanned: result.rescanned,
      bytesRead: result.bytesRead,
      invalidRecords: result.invalidRecords,
    };
  }

  const context = await getCodexContext({
    sourcePath: options.sourcePath,
    values: result.values,
  });
  let parentEventId: string | null = null;

  const events = result.values.flatMap((line) => {
    const event = parseRecord({ ...line, context });

    if (event === null) {
      return [];
    }

    const chained = { ...event, parentEventId };

    parentEventId = event.eventId;

    return [chained];
  });

  return {
    source: "codex",
    sourcePath: options.sourcePath,
    events,
    cursor: result.cursor,
    rescanned: result.rescanned,
    bytesRead: result.bytesRead,
    invalidRecords: result.invalidRecords,
  };
}

export async function discoverCodexFiles(
  sessionsDirectory: string,
): Promise<readonly string[]> {
  if (!existsSync(sessionsDirectory)) {
    return [];
  }

  const files: string[] = [];

  for await (const sourcePath of new Bun.Glob("**/rollout-*.jsonl").scan({
    cwd: sessionsDirectory,
    absolute: true,
    onlyFiles: true,
  })) {
    files.push(sourcePath);
  }

  return files.sort();
}
