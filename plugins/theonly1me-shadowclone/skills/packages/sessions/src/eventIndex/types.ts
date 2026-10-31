import type { SourceId } from "@shadowclone/core";
import type { AgentEventKind, TextRef, ToolCall } from "../observe";

export type IngestSummary = {
  readonly files: number;
  readonly events: number;
  readonly sessions: number;
  readonly bytesRead: number;
  readonly rescannedFiles: number;
  readonly invalidRecords: number;
};

export type CorpusSummary = {
  readonly sessions: number;
  readonly bytes: number;
  readonly activeDays: number;
};

export type IndexedEvent = {
  readonly id: number;
  readonly sourcePath: string;
  readonly source: SourceId;
  readonly sessionId: string;
  readonly eventId: string;
  readonly parentEventId: string | null;
  readonly timestamp: number;
  readonly cwd: string;
  readonly gitBranch: string | null;
  readonly kind: AgentEventKind;
  readonly tool: ToolCall | null;
  readonly isError: boolean;
  readonly textRef: TextRef | null;
};
