import type { Database } from "bun:sqlite";

const schemaVersion = 7;

const retiredSourcePurge = `
  DELETE FROM events WHERE source = 'shell';
  DELETE FROM cursors WHERE source = 'shell';
  DELETE FROM origin_binding_timeline WHERE source = 'shell';
  DELETE FROM origin_bindings WHERE origin_key LIKE '["shell",%';
`;

function resetOutdatedSchema(database: Database): void {
  const version = database
    .query<{ readonly user_version: number }, []>("PRAGMA user_version")
    .get()?.user_version;

  if (
    version === schemaVersion ||
    version === 6 ||
    version === 5 ||
    version === 4 ||
    version === 3
  ) {
    return;
  }

  database.exec(`
    DROP TABLE IF EXISTS events;
    DROP TABLE IF EXISTS cursors;
  `);
}

export function createSchema(database: Database): void {
  const previousVersion = database
    .query<{ user_version: number }, []>("PRAGMA user_version")
    .get()?.user_version;

  resetOutdatedSchema(database);

  const columns = database
    .query<{ name: string }, []>("PRAGMA table_info(cursors)")
    .all();

  if (
    columns.length > 0 &&
    !columns.some((column) => column.name === "identity")
  ) {
    database.exec(
      "ALTER TABLE cursors ADD COLUMN identity TEXT; ALTER TABLE cursors ADD COLUMN discarding INTEGER NOT NULL DEFAULT 0; ALTER TABLE cursors ADD COLUMN omitted_records INTEGER NOT NULL DEFAULT 0;",
    );
  }

  database.exec(`
    PRAGMA journal_mode = WAL;
    PRAGMA foreign_keys = ON;

    CREATE TABLE IF NOT EXISTS cursors (
      source_path TEXT PRIMARY KEY,
      source TEXT NOT NULL,
      byte_size INTEGER NOT NULL,
      modified_at REAL NOT NULL,
      byte_offset INTEGER NOT NULL,
      identity TEXT,
      discarding INTEGER NOT NULL DEFAULT 0,
      omitted_records INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS events (
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

    CREATE TABLE IF NOT EXISTS origin_observation (
      singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
      started_at INTEGER NOT NULL
    );

    INSERT OR IGNORE INTO origin_observation VALUES (1, ${Date.now()});

    CREATE TABLE IF NOT EXISTS origin_bindings (
      origin_key TEXT PRIMARY KEY,
      repository_id TEXT NOT NULL,
      repository_name TEXT,
      profile_file_name TEXT,
      origin_id TEXT NOT NULL,
      origin_directory TEXT NOT NULL,
      origin_promotable INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS origin_binding_timeline (
      source TEXT NOT NULL,
      session_id TEXT NOT NULL,
      effective_at INTEGER NOT NULL,
      repository_id TEXT NOT NULL,
      repository_name TEXT,
      profile_file_name TEXT,
      origin_id TEXT NOT NULL,
      origin_directory TEXT NOT NULL,
      origin_promotable INTEGER NOT NULL,
      PRIMARY KEY (source, session_id, effective_at)
    );

    CREATE INDEX IF NOT EXISTS events_source_path
      ON events(source_path);
    CREATE INDEX IF NOT EXISTS events_session
      ON events(source, session_id);
    CREATE INDEX IF NOT EXISTS events_kind
      ON events(kind);
    CREATE INDEX IF NOT EXISTS origin_binding_timeline_lookup
      ON origin_binding_timeline(source, session_id, effective_at DESC);

    PRAGMA user_version = ${schemaVersion};
  `);

  if (previousVersion === 3 || previousVersion === 4) {
    database.exec(`
    INSERT OR IGNORE INTO origin_bindings
      SELECT DISTINCT json_array(events.source, events.session_id, events.cwd),
        binding.repository_id, binding.repository_name, binding.profile_file_name,
        binding.origin_id, binding.origin_directory, binding.origin_promotable
      FROM events JOIN origin_bindings AS binding ON binding.origin_key = events.cwd;

    `);
  }

  if (previousVersion !== schemaVersion) {
    database.exec(retiredSourcePurge);
  }
}
