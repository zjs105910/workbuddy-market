import type { Database } from "bun:sqlite";
import type { ObservationBatch } from "../observe";

export function saveObservationBatch(options: {
  readonly database: Database;
  readonly batch: ObservationBatch;
}): void {
  const save = options.database.transaction(
    (observationBatch: ObservationBatch) => {
      if (observationBatch.rescanned) {
        options.database
          .query<void, [string]>("DELETE FROM events WHERE source_path = ?")
          .run(observationBatch.sourcePath);
      }

      const insert = options.database.query<
        void,
        [
          string,
          string,
          string,
          string,
          string | null,
          number,
          string,
          string | null,
          string,
          string | null,
          string | null,
          number,
          string | null,
        ]
      >(
        `INSERT INTO events (
          source_path, source, session_id, event_id, parent_event_id,
          timestamp, cwd, git_branch, kind, tool_use_id, tool_name,
          is_error, text_ref
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      );

      for (const event of observationBatch.events) {
        insert.run(
          observationBatch.sourcePath,
          event.source,
          event.sessionId,
          event.eventId,
          event.parentEventId,
          event.timestamp,
          event.cwd,
          event.gitBranch,
          event.kind,
          event.tool?.toolUseId ?? null,
          event.tool?.name ?? null,
          event.isError ? 1 : 0,
          event.textRef === null ? null : JSON.stringify(event.textRef),
        );
      }

      options.database
        .query<
          void,
          [
            string,
            string,
            number,
            number,
            number,
            string | null,
            number,
            number,
          ]
        >(
          `INSERT INTO cursors (
            source_path, source, byte_size, modified_at, byte_offset, identity, discarding, omitted_records
          ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
          ON CONFLICT(source_path) DO UPDATE SET
            source = excluded.source,
            byte_size = excluded.byte_size,
            modified_at = excluded.modified_at,
            byte_offset = excluded.byte_offset,
            identity = excluded.identity, discarding = excluded.discarding, omitted_records = excluded.omitted_records`,
        )
        .run(
          observationBatch.sourcePath,
          observationBatch.source,
          observationBatch.cursor.byteSize,
          observationBatch.cursor.modifiedAt,
          observationBatch.cursor.byteOffset,
          observationBatch.cursor.identity ?? null,
          observationBatch.cursor.discarding ? 1 : 0,
          observationBatch.cursor.omittedRecords ?? 0,
        );
    },
  );

  save(options.batch);
}
