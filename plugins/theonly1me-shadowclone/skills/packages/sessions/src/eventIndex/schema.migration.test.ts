import { expect, test } from "bun:test";
import { Database } from "bun:sqlite";
import { createSchema } from "./schema";

test("version five indexes gain the binding timeline without losing events", () => {
  const database = new Database(":memory:");

  database.exec(`
    CREATE TABLE events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      source_path TEXT NOT NULL,
      source TEXT NOT NULL,
      session_id TEXT NOT NULL,
      event_id TEXT NOT NULL,
      parent_event_id TEXT,
      timestamp INTEGER NOT NULL,
      cwd TEXT NOT NULL,
      git_branch TEXT,
      kind TEXT NOT NULL,
      tool_use_id TEXT,
      tool_name TEXT,
      is_error INTEGER NOT NULL,
      text_ref TEXT
    );
    INSERT INTO events (
      source_path, source, session_id, event_id, timestamp, cwd, kind, is_error
    ) VALUES ('source', 'antigravity', 'session', 'event', 1, '', 'user-prompt', 0);
    PRAGMA user_version = 5;
  `);
  createSchema(database);

  expect(
    database
      .query<{ readonly count: number }, []>(
        "SELECT COUNT(*) AS count FROM events",
      )
      .get()?.count,
  ).toBe(1);
  expect(
    database
      .query<{ readonly name: string }, []>(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'origin_binding_timeline'",
      )
      .get()?.name,
  ).toBe("origin_binding_timeline");
  expect(
    database
      .query<{ readonly user_version: number }, []>("PRAGMA user_version")
      .get()?.user_version,
  ).toBe(7);

  database.close();
});

test("version six indexes lose retired shell history rows and keep other sources", () => {
  const database = new Database(":memory:");

  createSchema(database);
  database.exec(`
    INSERT INTO events (
      source_path, source, session_id, event_id, timestamp, cwd, kind, is_error
    ) VALUES
      ('history', 'shell', 'shell-history', 'shell:0', 1, '', 'user-prompt', 0),
      ('session', 'codex', 'session', 'event', 1, '', 'user-prompt', 0);
    INSERT INTO cursors (source_path, source, byte_size, modified_at, byte_offset)
    VALUES ('history', 'shell', 1, 1, 1), ('session', 'codex', 1, 1, 1);
    INSERT INTO origin_bindings VALUES
      ('["shell","shell-history",""]', 'repository', NULL, NULL, 'origin', '/repository', 0),
      ('["codex","session",""]', 'repository', NULL, NULL, 'origin', '/repository', 0);
    INSERT INTO origin_binding_timeline VALUES
      ('shell', 'shell-history', 1, 'repository', NULL, NULL, 'origin', '/repository', 0),
      ('codex', 'session', 1, 'repository', NULL, NULL, 'origin', '/repository', 0);
    PRAGMA user_version = 6;
  `);
  createSchema(database);

  const sources = (table: string) =>
    database
      .query<{ readonly source: string }, []>(`SELECT source FROM ${table}`)
      .all()
      .map((row) => row.source);

  expect(sources("events")).toEqual(["codex"]);
  expect(sources("cursors")).toEqual(["codex"]);
  expect(sources("origin_binding_timeline")).toEqual(["codex"]);
  expect(
    database
      .query<{ readonly origin_key: string }, []>(
        "SELECT origin_key FROM origin_bindings",
      )
      .all()
      .map((row) => row.origin_key),
  ).toEqual(['["codex","session",""]']);

  database.close();
});
