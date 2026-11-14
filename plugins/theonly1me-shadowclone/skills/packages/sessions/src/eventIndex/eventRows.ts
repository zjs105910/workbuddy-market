import { parseTextRef, type TextRef } from "../observe";
import type { IndexedEvent } from "./types";

export type CursorRow = {
  readonly source_path: string;
  readonly byte_size: number;
  readonly modified_at: number;
  readonly byte_offset: number;
  readonly identity: string | null;
  readonly discarding: number;
  readonly omitted_records: number;
};

export type EventRow = {
  readonly id: number;
  readonly source_path: string;
  readonly source: IndexedEvent["source"];
  readonly session_id: string;
  readonly event_id: string;
  readonly parent_event_id: string | null;
  readonly timestamp: number;
  readonly cwd: string;
  readonly git_branch: string | null;
  readonly kind: IndexedEvent["kind"];
  readonly tool_use_id: string | null;
  readonly tool_name: string | null;
  readonly is_error: number;
  readonly text_ref: string | null;
};

function textRefFromRow(value: string | null): TextRef | null {
  if (value === null) {
    return null;
  }

  try {
    return parseTextRef(JSON.parse(value));
  } catch {
    return null;
  }
}

export function toIndexedEvent(row: EventRow): IndexedEvent {
  return {
    id: row.id,
    sourcePath: row.source_path,
    source: row.source,
    sessionId: row.session_id,
    eventId: row.event_id,
    parentEventId: row.parent_event_id,
    timestamp: row.timestamp,
    cwd: row.cwd,
    gitBranch: row.git_branch,
    kind: row.kind,
    tool:
      row.tool_name === null
        ? null
        : { toolUseId: row.tool_use_id, name: row.tool_name },
    isError: row.is_error === 1,
    textRef: textRefFromRow(row.text_ref),
  };
}
