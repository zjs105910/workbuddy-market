import { expect, test } from "bun:test";
import type { SourceId } from "@shadowclone/core";
import type { AgentEvent } from "../observe";
import { checkMarkerStaleness, computeSourceHealth } from "./health";

function mockEvent(options: {
  readonly source: SourceId;
  readonly sessionId: string;
  readonly kind: AgentEvent["kind"];
}): AgentEvent {
  return {
    source: options.source,
    sessionId: options.sessionId,
    eventId: `${options.source}:${options.sessionId}:${Math.random()}`,
    parentEventId: null,
    timestamp: Date.now(),
    cwd: "/repo",
    gitBranch: "main",
    kind: options.kind,
    tool: null,
    isError: false,
    textRef: null,
  };
}

test("computes per-source sessions, interruptions, and denials", () => {
  const events: AgentEvent[] = [
    mockEvent({
      source: "claude-code",
      sessionId: "s1",
      kind: "interruption",
    }),
    mockEvent({
      source: "claude-code",
      sessionId: "s1",
      kind: "permission-denied",
    }),
    mockEvent({
      source: "claude-code",
      sessionId: "s2",
      kind: "user-prompt",
    }),
    mockEvent({
      source: "cursor",
      sessionId: "c1",
      kind: "user-prompt",
    }),
  ];

  const health = computeSourceHealth(events);
  const claude = health.find((h) => h.source === "claude-code");
  const cursor = health.find((h) => h.source === "cursor");

  expect(claude?.sessions).toBe(2);
  expect(claude?.interruptions).toBe(1);
  expect(claude?.denials).toBe(1);
  expect(claude?.isStale).toBeFalse();

  expect(cursor?.sessions).toBe(1);
  expect(cursor?.interruptions).toBe(0);
  expect(cursor?.denials).toBe(0);
  expect(cursor?.isStale).toBeFalse();
});

test("flags stale markers when Claude Code has 25+ sessions with zero signals", () => {
  const events: AgentEvent[] = [];

  for (let i = 0; i < 25; i++) {
    events.push(
      mockEvent({
        source: "claude-code",
        sessionId: `session-${i}`,
        kind: "user-prompt",
      }),
    );
  }

  const warnings = checkMarkerStaleness(events);

  expect(warnings.length).toBe(1);
  expect(warnings[0]).toContain('Source "claude-code" has 25 sessions');
  expect(warnings[0]).toContain("Marker patterns may be stale");
});

test("does not flag staleness when signals are present", () => {
  const events: AgentEvent[] = [];

  for (let i = 0; i < 25; i++) {
    events.push(
      mockEvent({
        source: "claude-code",
        sessionId: `session-${i}`,
        kind: i === 0 ? "interruption" : "user-prompt",
      }),
    );
  }

  const warnings = checkMarkerStaleness(events);

  expect(warnings.length).toBe(0);
});
