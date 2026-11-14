import type { CorpusSummary, IndexedEvent } from "./eventIndex";

export const signalCorpus: CorpusSummary = {
  sessions: 2,
  bytes: 2_097_152,
  activeDays: 1,
};

function event(options: {
  readonly id: number;
  readonly sessionId: string;
  readonly cwd: string;
  readonly kind: IndexedEvent["kind"];
  readonly toolName?: string;
}): IndexedEvent {
  return {
    id: options.id,
    sourcePath: "/fixture.jsonl",
    source: "claude-code",
    sessionId: options.sessionId,
    eventId: `event-${options.id}`,
    parentEventId: null,
    timestamp: 1_788_537_600_000 + options.id,
    cwd: options.cwd,
    gitBranch: "feat/mirror",
    kind: options.kind,
    tool: options.toolName
      ? { toolUseId: `tool-${options.id}`, name: options.toolName }
      : null,
    isError: false,
    textRef: null,
  };
}

export const signalEvents = [
  event({
    id: 1,
    sessionId: "one",
    cwd: "/one",
    kind: "tool-call",
    toolName: "Edit",
  }),
  event({
    id: 2,
    sessionId: "one",
    cwd: "/one",
    kind: "interruption",
  }),
  event({
    id: 3,
    sessionId: "one",
    cwd: "/one",
    kind: "question-asked",
    toolName: "AskUserQuestion",
  }),
  event({
    id: 4,
    sessionId: "one",
    cwd: "/one",
    kind: "user-prompt",
  }),
  event({
    id: 5,
    sessionId: "two",
    cwd: "/two",
    kind: "tool-call",
    toolName: "Edit",
  }),
  event({
    id: 6,
    sessionId: "two",
    cwd: "/two",
    kind: "interruption",
  }),
] as const;
