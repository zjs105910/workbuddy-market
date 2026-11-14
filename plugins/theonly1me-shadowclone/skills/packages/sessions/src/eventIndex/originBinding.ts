import { originDirectoryName } from "../signal/origin/remote";
import type { Database } from "bun:sqlite";

export type BoundRepository = {
  readonly id: string;
  readonly name: string | null;
  readonly profileFileName: string | null;
  readonly origin: {
    readonly id: string;
    readonly directoryName: string;
    readonly promotable: boolean;
  };
};

type BindingRow = {
  readonly repository_id: string;
  readonly repository_name: string | null;
  readonly profile_file_name: string | null;
  readonly origin_id: string;
  readonly origin_directory: string;
  readonly origin_promotable: number;
};

function bindingFromRow(row: BindingRow): BoundRepository {
  return {
    id: row.repository_id,
    name: row.repository_name,
    profileFileName: row.profile_file_name,
    origin: {
      id: row.origin_id,
      directoryName: originDirectoryName(row.origin_id),
      promotable: row.origin_promotable === 1,
    },
  };
}

export function readOriginBinding(options: {
  readonly database: Database;
  readonly originKey: string;
}): BoundRepository | null {
  const row = options.database
    .query<BindingRow, [string]>(
      `SELECT repository_id, repository_name, profile_file_name,
        origin_id, origin_directory, origin_promotable
      FROM origin_bindings WHERE origin_key = ?`,
    )
    .get(options.originKey);

  return row === null ? null : bindingFromRow(row);
}

export function writeOriginBinding(options: {
  readonly database: Database;
  readonly originKey: string;
  readonly repository: BoundRepository;
}): void {
  options.database
    .query(
      `INSERT OR IGNORE INTO origin_bindings (
        origin_key, repository_id, repository_name, profile_file_name,
        origin_id, origin_directory, origin_promotable
      ) VALUES (?, ?, ?, ?, ?, ?, ?)`,
    )
    .run(
      options.originKey,
      options.repository.id,
      options.repository.name,
      options.repository.profileFileName,
      options.repository.origin.id,
      options.repository.origin.directoryName,
      options.repository.origin.promotable ? 1 : 0,
    );
}

export function readSessionOriginBinding(options: {
  readonly database: Database;
  readonly source: string;
  readonly sessionId: string;
  readonly timestamp: number;
}): BoundRepository | null {
  const row = options.database
    .query<BindingRow, [string, string, number]>(
      `SELECT repository_id, repository_name, profile_file_name,
        origin_id, origin_directory, origin_promotable
      FROM origin_binding_timeline
      WHERE source = ? AND session_id = ? AND effective_at <= ?
      ORDER BY effective_at DESC LIMIT 1`,
    )
    .get(options.source, options.sessionId, options.timestamp);

  return row === null ? null : bindingFromRow(row);
}

export function writeSessionOriginBinding(options: {
  readonly database: Database;
  readonly source: string;
  readonly sessionId: string;
  readonly timestamp: number;
  readonly repository: BoundRepository;
}): void {
  options.database
    .query(
      `INSERT INTO origin_binding_timeline (
      source, session_id, effective_at, repository_id, repository_name,
      profile_file_name, origin_id, origin_directory, origin_promotable
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(source, session_id, effective_at) DO UPDATE SET
      repository_id = excluded.repository_id,
      repository_name = excluded.repository_name,
      profile_file_name = excluded.profile_file_name,
      origin_id = excluded.origin_id,
      origin_directory = excluded.origin_directory,
      origin_promotable = excluded.origin_promotable`,
    )
    .run(
      options.source,
      options.sessionId,
      options.timestamp,
      options.repository.id,
      options.repository.name,
      options.repository.profileFileName,
      options.repository.origin.id,
      options.repository.origin.directoryName,
      options.repository.origin.promotable ? 1 : 0,
    );
}
