import { expect, test } from "bun:test";
import { Database } from "bun:sqlite";
import { chmod, mkdir, mkdtemp, readdir, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { openCursorDatabase } from "./cursorDatabase";

test("a WAL store in a read-only folder opens through the immutable fallback", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "cursor store ?#%-"));
  const directory = path.join(root, "workspace");
  const sourcePath = path.join(directory, "store.db");

  await mkdir(directory);

  const writer = new Database(sourcePath);

  writer.run("PRAGMA journal_mode=WAL");
  writer.run("CREATE TABLE meta (key TEXT, value TEXT)");
  writer.run("INSERT INTO meta VALUES ('title', 'synthetic')");
  writer.run("PRAGMA wal_checkpoint(TRUNCATE)");
  writer.close();

  await rm(`${sourcePath}-wal`, { force: true });
  await rm(`${sourcePath}-shm`, { force: true });
  await chmod(directory, 0o500);

  try {
    const database = openCursorDatabase(sourcePath);

    try {
      expect(database.query("SELECT value FROM meta").get()).toEqual({ value: "synthetic" });
    } finally {
      database.close();
    }

    expect(await readdir(directory)).toEqual(["store.db"]);
  } finally {
    await chmod(directory, 0o700);
    await rm(root, { recursive: true, force: true });
  }
});
