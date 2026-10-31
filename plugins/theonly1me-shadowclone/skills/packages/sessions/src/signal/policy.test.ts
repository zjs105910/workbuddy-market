import { expect, test } from "bun:test";
import type { IndexedEvent } from "../eventIndex";
import { deriveSignals } from "./index";

function interruptionEvent(options: {
  readonly id: number;
  readonly cwd: string;
  readonly sessionId: string;
}): IndexedEvent {
  return {
    id: options.id,
    sourcePath: "/fixture.jsonl",
    source: "claude-code",
    sessionId: options.sessionId,
    eventId: `event-${options.id}`,
    parentEventId: null,
    timestamp: 1_788_537_600_000,
    cwd: options.cwd,
    gitBranch: null,
    kind: "interruption",
    tool: null,
    isError: false,
    textRef: null,
  };
}

test("managed origin patterns remove matching events from derivation", async () => {
  const derived = await deriveSignals({
    events: [
      interruptionEvent({ id: 1, cwd: "/one", sessionId: "one" }),
      interruptionEvent({ id: 2, cwd: "/two", sessionId: "two" }),
    ],
    corpus: { sessions: 2, bytes: 20, activeDays: 1 },
    gitMetadataEnabled: true,
    readRemote: (cwd) =>
      Promise.resolve(
        cwd === "/one"
          ? "git@github.com:acme/repo.git"
          : "git@github.com:other/repo.git",
      ),
    blockedOrigins: ["github.com/acme/repo"],
  });

  expect(derived.events).toHaveLength(1);
  expect(derived.corrections[0]?.origin.id).toBe("github.com/other");
});
