import { Database } from "bun:sqlite";
import { expect, test } from "bun:test";
import { mkdir, mkdtemp, unlink } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { cursorStoreSignature, readCursorStore } from "./cursorStore";

function encodeBlob(value: unknown): Uint8Array {
  return new TextEncoder().encode(JSON.stringify(value));
}

function hex(value: string): string {
  return [...new TextEncoder().encode(value)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

test("reads a Cursor database configured in WAL mode without active shm/wal files", async () => {
  const temporaryDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-cursor-wal-"),
  );
  const sessionDirectory = path.join(temporaryDirectory, "session-1");

  await mkdir(sessionDirectory, { recursive: true });

  const sourcePath = path.join(sessionDirectory, "store.db");

  const database = new Database(sourcePath, { create: true, strict: true });

  database.exec("PRAGMA journal_mode=WAL;");
  database.exec(
    "CREATE TABLE blobs (id TEXT PRIMARY KEY, data BLOB); CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);",
  );

  const insertBlob = database.query<void, [string, Uint8Array]>(
    "INSERT INTO blobs (id, data) VALUES (?, ?)",
  );

  insertBlob.run(
    "blob-1",
    encodeBlob({
      role: "user",
      content: [{ type: "text", text: "hello cursor" }],
    }),
  );
  database
    .query<void, [string]>("INSERT INTO meta (key, value) VALUES ('0', ?)")
    .run(
      hex(
        JSON.stringify({
          agentId: "wal-session",
          createdAt: 1_788_537_600_000,
        }),
      ),
    );
  database.close();

  await unlink(`${sourcePath}-shm`).catch(() => null);
  await unlink(`${sourcePath}-wal`).catch(() => null);

  const signature = await cursorStoreSignature(sourcePath);

  if (signature === null) {
    throw new Error("Expected valid file signature");
  }

  const store = await readCursorStore({ sourcePath, signature });

  if (store === null) {
    throw new Error("Expected store to be read successfully in WAL mode");
  }

  expect(store.sessionId).toBe("wal-session");
  expect(store.blobs.length).toBe(1);

  const [firstBlob] = store.blobs;

  expect(firstBlob?.id).toBe("blob-1");
});

test("reads a Cursor database with active WAL frames", async () => {
  const temporaryDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-cursor-active-wal-"),
  );
  const sessionDirectory = path.join(temporaryDirectory, "session-2");

  await mkdir(sessionDirectory, { recursive: true });

  const sourcePath = path.join(sessionDirectory, "store.db");

  const writer = new Database(sourcePath, { create: true, strict: true });

  writer.exec("PRAGMA journal_mode=WAL;");
  writer.exec(
    "CREATE TABLE blobs (id TEXT PRIMARY KEY, data BLOB); CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);",
  );

  const insertBlob = writer.query<void, [string, Uint8Array]>(
    "INSERT INTO blobs (id, data) VALUES (?, ?)",
  );

  insertBlob.run(
    "blob-1",
    encodeBlob({
      role: "user",
      content: [{ type: "text", text: "first turn" }],
    }),
  );
  writer.exec("PRAGMA wal_checkpoint(TRUNCATE);");

  insertBlob.run(
    "blob-2",
    encodeBlob({
      role: "assistant",
      content: [{ type: "text", text: "second turn" }],
    }),
  );
  writer
    .query<void, [string]>("INSERT INTO meta (key, value) VALUES ('0', ?)")
    .run(
      hex(
        JSON.stringify({
          agentId: "active-wal-session",
          createdAt: 1_788_537_700_000,
        }),
      ),
    );

  const signature = await cursorStoreSignature(sourcePath);

  if (signature === null) {
    writer.close();

    throw new Error("Expected valid signature");
  }

  const store = await readCursorStore({ sourcePath, signature });

  writer.close();

  if (store === null) {
    throw new Error("Expected active WAL store to be readable");
  }

  expect(store.sessionId).toBe("active-wal-session");
  expect(store.blobs.length).toBe(2);
});

test("returns null and does not throw when cursor database is corrupt", async () => {
  const temporaryDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-cursor-corrupt-"),
  );
  const sourcePath = path.join(temporaryDirectory, "store.db");

  await Bun.write(sourcePath, "not a valid sqlite file");

  const signature = {
    size: 23,
    modifiedAt: Date.now(),
  };

  const store = await readCursorStore({ sourcePath, signature });

  expect(store).toBeNull();
});
