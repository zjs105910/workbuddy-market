import { Database } from "bun:sqlite";
import { expect, test } from "bun:test";
import { mkdir, mkdtemp, readdir } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { defaultConfig, createProjectPaths } from "@shadowclone/core";
import { ingestSources, openEventIndex } from "./index";

const plantedSecret = ["sk", "proj", "indexSecret123456789"].join("-");

async function createCorpus(): Promise<{
  readonly homeDirectory: string;
  readonly databasePath: string;
}> {
  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-index-"),
  );

  const transcriptDirectory = path.join(
    homeDirectory,
    ".claude",
    "projects",
    "fixture",
  );

  await mkdir(transcriptDirectory, { recursive: true });

  const record = {
    type: "user",
    sessionId: "session-1",
    uuid: "event-1",
    timestamp: "2026-09-05T08:00:00.000Z",
    cwd: "/repo",
    message: { id: "message-1", content: plantedSecret },
  };

  await Bun.write(
    path.join(transcriptDirectory, "session-1.jsonl"),
    `${JSON.stringify(record)}\n`,
  );

  return {
    homeDirectory,
    databasePath: path.join(homeDirectory, ".shadowclone", "index.db"),
  };
}

test("indexes skeletons incrementally without captured text", async () => {
  const corpus = await createCorpus();
  const paths = createProjectPaths({
    homeDirectory: corpus.homeDirectory,
    platform: "darwin",
  });
  const config = {
    ...defaultConfig,
    sources: { ...defaultConfig.sources, "claude-code": true },
  };
  const index = await openEventIndex(corpus.databasePath);

  const first = await ingestSources({ index, config, paths });
  const second = await ingestSources({ index, config, paths });

  index.close();

  expect(first.events).toBe(1);
  expect(first.bytesRead).toBeGreaterThan(0);
  expect(second.events).toBe(0);
  expect(second.bytesRead).toBe(0);

  const indexDirectory = path.dirname(corpus.databasePath);
  const indexFiles = await readdir(indexDirectory);

  for (const fileName of indexFiles) {
    const bytes = await Bun.file(path.join(indexDirectory, fileName)).bytes();

    expect(new TextDecoder().decode(bytes)).not.toContain(plantedSecret);
  }
});

test("rebuilds an outdated disposable index schema", async () => {
  const directory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-schema-"),
  );
  const databasePath = path.join(directory, "index.db");
  const legacy = new Database(databasePath, { create: true });

  legacy.exec(`
    CREATE TABLE cursors (source_path TEXT PRIMARY KEY);
    CREATE TABLE events (id INTEGER PRIMARY KEY);
    INSERT INTO events (id) VALUES (1);
  `);
  legacy.close();

  const index = await openEventIndex(databasePath);

  expect(index.countEvents()).toBe(0);

  index.close();
});
