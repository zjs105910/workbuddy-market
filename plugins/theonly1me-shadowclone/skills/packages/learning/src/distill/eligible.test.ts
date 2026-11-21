import { expect, test } from "bun:test";
import type { IndexedEvent, CorrectionSignal } from "@shadowclone/sessions";
import { defaultConfig } from "@shadowclone/core";
import {
  allowlistedSignals,
  authorizedLearningEvents,
  isEligibleForDistillation,
} from "./index";

function indexedEvent(kind: IndexedEvent["kind"]): IndexedEvent {
  return {
    id: 1,
    sourcePath: "/fixture.jsonl",
    source: "claude-code",
    sessionId: "session",
    eventId: "event",
    parentEventId: null,
    timestamp: 0,
    cwd: "/repo",
    gitBranch: null,
    kind,
    tool: null,
    isError: false,
    textRef: {
      type: "file",
      sourcePath: "/fixture.jsonl",
      byteOffset: 0,
      byteLength: 10,
    },
  };
}

test("allows only user-authored events with text pointers", () => {
  expect(isEligibleForDistillation(indexedEvent("user-prompt"))).toBeTrue();
  expect(isEligibleForDistillation(indexedEvent("question-answered"))).toBeTrue();
  expect(isEligibleForDistillation(indexedEvent("plan-resolved"))).toBeTrue();
  expect(isEligibleForDistillation(indexedEvent("question-asked"))).toBeFalse();
  expect(isEligibleForDistillation(indexedEvent("plan-presented"))).toBeFalse();
});

test("removes indexed events after their source is disabled", () => {
  const event = indexedEvent("user-prompt");
  const disabled = authorizedLearningEvents({
    events: [event],
    config: defaultConfig,
  });
  const enabled = authorizedLearningEvents({
    events: [event],
    config: {
      ...defaultConfig,
      sources: { ...defaultConfig.sources, "claude-code": true },
    },
  });

  expect(disabled).toEqual([]);
  expect(enabled).toEqual([event]);
});

test("rejects tool results and thinking even if a pointer is present", () => {
  expect(isEligibleForDistillation(indexedEvent("tool-call"))).toBeFalse();
  expect(isEligibleForDistillation(indexedEvent("tool-result"))).toBeFalse();
  expect(isEligibleForDistillation(indexedEvent("thinking"))).toBeFalse();
  expect(isEligibleForDistillation(indexedEvent("assistant-text"))).toBeFalse();
});

test("removes a tool result pointer before a distillation batch", () => {
  const event = indexedEvent("tool-result");
  const ref = event.textRef;

  if (ref === null) {
    throw new Error("Expected fixture pointer");
  }

  const signal: CorrectionSignal = {
    kind: "interruption",
    category: "fixture",
    label: "fixture",
    sessionId: "session",
    timestamp: 0,
    origin: {
      id: "github.com/acme",
      directoryName: "github.com--acme--936913df4a5c268b",
      promotable: true,
    },
    repositoryName: null,
    textRefs: [ref],
  };

  expect(
    allowlistedSignals({ signals: [signal], events: [event] })[0]?.textRefs,
  ).toEqual([]);
});

test("keeps assistant text as context and never as evidence", () => {
  const event = indexedEvent("assistant-text");
  const ref = event.textRef;

  if (ref === null) {
    throw new Error("Expected fixture pointer");
  }

  const signal: CorrectionSignal = {
    kind: "interruption",
    category: "assistant-text",
    label: "during an explanation",
    sessionId: "session",
    timestamp: 0,
    origin: {
      id: "github.com/acme",
      directoryName: "github.com--acme--936913df4a5c268b",
      promotable: true,
    },
    repositoryName: null,
    textRefs: [ref],
    contextRefs: [ref],
  };
  const [allowed] = allowlistedSignals({ signals: [signal], events: [event] });

  expect(allowed?.textRefs).toEqual([]);
  expect(allowed?.contextRefs).toEqual([ref]);
});
