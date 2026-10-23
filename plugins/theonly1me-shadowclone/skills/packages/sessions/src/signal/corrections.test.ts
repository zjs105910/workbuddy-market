import { expect, test } from "bun:test";
import type { IndexedEvent } from "../eventIndex";
import type { FileTextRef } from "../observe";
import { mineCorrections } from "./corrections";

function fileRef(byteOffset: number): FileTextRef {
  return {
    type: "file",
    sourcePath: "/fixture.jsonl",
    byteOffset,
    byteLength: 10,
  };
}

function indexedEvent(options: {
  readonly id: number;
  readonly kind: IndexedEvent["kind"];
  readonly textRef: FileTextRef;
}): IndexedEvent {
  return {
    id: options.id,
    sourcePath: "/fixture.jsonl",
    source: "claude-code",
    sessionId: "session",
    eventId: `event-${options.id}`,
    parentEventId: null,
    timestamp: options.id,
    cwd: "/repository",
    gitBranch: null,
    kind: options.kind,
    tool: null,
    isError: false,
    textRef: options.textRef,
  };
}

test("uses the agent question as context and the user answer as evidence", () => {
  const questionRef = fileRef(0);
  const answerRef = fileRef(100);
  const [signal] = mineCorrections({
    events: [
      indexedEvent({ id: 1, kind: "question-asked", textRef: questionRef }),
      indexedEvent({ id: 2, kind: "user-prompt", textRef: answerRef }),
    ],
    repositories: new Map(),
  });

  expect(signal?.kind).toBe("question-answered");
  expect(signal?.textRefs).toEqual([answerRef]);
  expect(signal?.contextRefs).toEqual([questionRef]);
});

test("uses the presented plan as context and the user response as evidence", () => {
  const planRef = fileRef(0);
  const responseRef = fileRef(100);
  const [signal] = mineCorrections({
    events: [
      indexedEvent({ id: 1, kind: "plan-presented", textRef: planRef }),
      indexedEvent({ id: 2, kind: "plan-resolved", textRef: responseRef }),
    ],
    repositories: new Map(),
  });

  expect(signal?.kind).toBe("plan-resolved");
  expect(signal?.textRefs).toEqual([responseRef]);
  expect(signal?.contextRefs).toEqual([planRef]);
});
