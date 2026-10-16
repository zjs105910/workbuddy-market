import { expect, test } from "bun:test";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { maximumTranscriptWindowBytes } from "@shadowclone/core";
import { readJsonLines } from "./cursor";

test("oversized records drain across bounded windows without losing the next record", async () => {
  const directory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-window-"),
  );

  try {
    const sourcePath = path.join(directory, "session.jsonl");

    await Bun.write(
      sourcePath,
      `${"x".repeat(maximumTranscriptWindowBytes + 1024)}\n{"next":true}\n`,
    );

    const first = await readJsonLines({ sourcePath, cursor: null });

    expect(first?.bytesRead).toBe(maximumTranscriptWindowBytes);
    expect(first?.cursor.discarding).toBeTrue();
    expect(first?.cursor.omittedRecords).toBe(1);

    const second = await readJsonLines({
      sourcePath,
      cursor: first?.cursor ?? null,
    });

    expect(second?.values.map((entry) => entry.value)).toEqual([
      { next: true },
    ]);
    expect(second?.cursor.discarding).toBeFalse();
    expect(second?.cursor.omittedRecords).toBe(1);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
