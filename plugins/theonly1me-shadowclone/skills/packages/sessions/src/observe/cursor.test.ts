import { expect, test } from "bun:test";
import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { readJsonLines } from "./cursor";

async function createTranscript(contents: string): Promise<string> {
  const directory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-cursor-"),
  );
  const sourcePath = path.join(directory, "session.jsonl");

  await Bun.write(sourcePath, contents);

  return sourcePath;
}

test("advances only through complete JSONL records", async () => {
  const sourcePath = await createTranscript('{"value":1}\n{"value":');
  const first = await readJsonLines({ sourcePath, cursor: null });

  expect(first?.values).toHaveLength(1);
  expect(first?.cursor.byteOffset).toBe('{"value":1}\n'.length);

  await Bun.sleep(2);
  await Bun.write(sourcePath, '{"value":1}\n{"value":2}\n');

  const second = await readJsonLines({
    sourcePath,
    cursor: first?.cursor ?? null,
  });

  expect(second?.values).toHaveLength(1);
  expect(second?.values[0]?.value).toEqual({ value: 2 });
});

test("skips an invalid completed record without losing later records", async () => {
  const sourcePath = await createTranscript(
    '{"value":1}\nnot-json\n{"value":2}\n',
  );
  const result = await readJsonLines({ sourcePath, cursor: null });

  expect(result?.values.map((line) => line.value)).toEqual([
    { value: 1 },
    { value: 2 },
  ]);
  expect(result?.invalidRecords).toBe(1);
  expect(result?.cursor.byteOffset).toBe(
    '{"value":1}\nnot-json\n{"value":2}\n'.length,
  );
});

test("returns no bytes for an unchanged file", async () => {
  const sourcePath = await createTranscript('{"value":1}\n');
  const first = await readJsonLines({ sourcePath, cursor: null });
  const second = await readJsonLines({
    sourcePath,
    cursor: first?.cursor ?? null,
  });

  expect(second?.bytesRead).toBe(0);
  expect(second?.values).toHaveLength(0);
});

test("rescans when a file is truncated", async () => {
  const sourcePath = await createTranscript(
    '{"value":"first"}\n{"value":"second"}\n',
  );
  const first = await readJsonLines({ sourcePath, cursor: null });

  await Bun.sleep(2);
  await Bun.write(sourcePath, '{"value":"new"}\n');

  const second = await readJsonLines({
    sourcePath,
    cursor: first?.cursor ?? null,
  });

  expect(second?.rescanned).toBeTrue();
  expect(second?.values).toHaveLength(1);
  expect(second?.values[0]?.value).toEqual({ value: "new" });
});
