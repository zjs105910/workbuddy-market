import { getLineBoundaries, type CursorRead } from "./cursorRead";
import type { FileCursor, FileTextRef } from "./types";

export type { CursorRead } from "./cursorRead";

export type JsonLine = {
  readonly value: unknown;
  readonly ref: FileTextRef;
};

export async function readJsonLines(options: {
  readonly sourcePath: string;
  readonly cursor: FileCursor | null;
}): Promise<CursorRead<JsonLine> | null> {
  const result = await getLineBoundaries(options);

  if (result === null) {
    return null;
  }

  const decoder = new TextDecoder();
  const values: JsonLine[] = [];
  let invalidRecords = result.invalidRecords;

  for (const line of result.values) {
    try {
      values.push({
        value: JSON.parse(decoder.decode(line.bytes)),
        ref: line.ref,
      });
    } catch {
      invalidRecords += 1;
    }
  }

  return { ...result, values, invalidRecords };
}
