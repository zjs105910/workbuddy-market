import { toIndexedEvent, type CursorRow, type EventRow } from "./eventRows";
import type { Database } from "bun:sqlite";
import type { FileCursor, ObservationBatch } from "../observe";
import type { CorpusSummary, IndexedEvent } from "./types";
import {
  readOriginBinding,
  readSessionOriginBinding,
  writeOriginBinding,
  writeSessionOriginBinding,
  type BoundRepository,
} from "./originBinding";
import { saveObservationBatch } from "./write";

export class EventIndex {
  readonly #database: Database;

  constructor(database: Database) {
    this.#database = database;
  }

  getCursor(sourcePath: string): FileCursor | null {
    const row = this.#database
      .query<CursorRow, [string]>(
        `SELECT source_path, byte_size, modified_at, byte_offset, identity, discarding, omitted_records
         FROM cursors WHERE source_path = ?`,
      )
      .get(sourcePath);

    return row === null
      ? null
      : {
          sourcePath: row.source_path,
          byteSize: row.byte_size,
          modifiedAt: row.modified_at,
          byteOffset: row.byte_offset,
          ...(row.identity === null
            ? {}
            : {
                identity: row.identity,
                discarding: row.discarding === 1,
                omittedRecords: row.omitted_records,
              }),
        };
  }

  saveBatch(batch: ObservationBatch): void {
    saveObservationBatch({ database: this.#database, batch });
  }

  listEvents(): readonly IndexedEvent[] {
    return this.#database
      .query<EventRow, []>(
        `SELECT id, source_path, source, session_id, event_id,
          parent_event_id, timestamp, cwd, git_branch, kind, tool_use_id,
          tool_name, is_error, text_ref
        FROM events ORDER BY source, session_id, id`,
      )
      .all()
      .map(toIndexedEvent);
  }

  getCorpusSummary(): CorpusSummary {
    const row = this.#database
      .query<CorpusSummary, []>(
        `SELECT
          (SELECT COUNT(*) FROM (
            SELECT DISTINCT source, session_id FROM events
          )) AS sessions,
          COALESCE((SELECT SUM(byte_size) FROM cursors), 0) AS bytes,
          (SELECT COUNT(*) FROM (
            SELECT DISTINCT date(timestamp / 1000, 'unixepoch')
            FROM events WHERE timestamp > 0
          )) AS activeDays`,
      )
      .get();

    return row ?? { sessions: 0, bytes: 0, activeDays: 0 };
  }

  countEvents(): number {
    const row = this.#database
      .query<{ readonly count: number }, []>(
        "SELECT COUNT(*) AS count FROM events",
      )
      .get();

    return row?.count ?? 0;
  }

  countSessions(): number {
    return this.getCorpusSummary().sessions;
  }

  getOriginObservationStart(): number {
    return (
      this.#database
        .query<{ started_at: number }, []>(
          "SELECT started_at FROM origin_observation WHERE singleton = 1",
        )
        .get()?.started_at ?? Number.POSITIVE_INFINITY
    );
  }

  getOriginBinding(originKey: string): BoundRepository | null {
    return readOriginBinding({ database: this.#database, originKey });
  }

  bindOrigin(options: {
    readonly originKey: string;
    readonly repository: BoundRepository;
  }): void {
    writeOriginBinding({
      database: this.#database,
      originKey: options.originKey,
      repository: options.repository,
    });
  }

  getSessionOriginBinding(options: {
    readonly source: string;
    readonly sessionId: string;
    readonly timestamp: number;
  }): BoundRepository | null {
    return readSessionOriginBinding({ database: this.#database, ...options });
  }

  bindSessionOrigin(options: {
    readonly source: string;
    readonly sessionId: string;
    readonly timestamp: number;
    readonly repository: BoundRepository;
  }): void {
    writeSessionOriginBinding({ database: this.#database, ...options });
  }

  close(): void {
    this.#database.close();
  }
}
