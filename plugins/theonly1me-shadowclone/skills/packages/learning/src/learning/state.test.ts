import { expect, test } from "bun:test";
import { fingerprint } from "@shadowclone/core";
import type { CorrectionSignal } from "@shadowclone/sessions";
import {
  episodeId,
  selectLearningEpisodes,
  selectNewestLearningEpisodes,
  selectRequestedLearningEpisodes,
  type LearningState,
} from "./state";

function signal(timestamp: number): CorrectionSignal {
  return {
    kind: "interruption",
    category: "tool:Edit",
    label: "while using Edit",
    sessionId: `session-${timestamp}`,
    timestamp,
    origin: {
      id: "github.com/acme",
      directoryName: "github.com--acme",
      promotable: true,
    },
    repositoryName: null,
    textRefs: [],
  };
}

const idleState: LearningState = {
  lastAttemptAt: null,
  lastCompletedAt: null,
  status: "idle",
  processed: [],
};

test("learning selects the sixty newest pending episodes", () => {
  const now = 1_800_000_000_000;
  const signals = Array.from({ length: 65 }, (_, index) => signal(now - index));

  const selected = selectLearningEpisodes({ signals, state: idleState, now });

  expect(selected).toHaveLength(60);
  expect(selected[0]?.timestamp).toBe(now);
  expect(selected.at(-1)?.timestamp).toBe(now - 59);
});

test("learning keeps reaching episodes beyond the former thirty day horizon", () => {
  const now = 1_800_000_000_000;
  const ancient = now - 400 * 24 * 60 * 60 * 1_000;

  const selected = selectLearningEpisodes({
    signals: [signal(ancient)],
    state: idleState,
    now,
  });

  expect(selected.map((entry) => entry.timestamp)).toEqual([ancient]);
});

test("learning never revisits an episode recorded in the ledger", () => {
  const now = 1_800_000_000_000;
  const [first] = [signal(now - 2)];

  if (!first) {
    throw new Error("Fixture signal was unavailable");
  }

  const signals = [first, signal(now - 1)];
  const state: LearningState = {
    ...idleState,
    processed: [{ id: episodeId(first), timestamp: now - 2 }],
  };

  const selected = selectLearningEpisodes({ signals, state, now });

  expect(selected.map((entry) => entry.timestamp)).toEqual([now - 1]);
});

test("setup learning chooses the newest pending episodes first", () => {
  const now = 1_800_000_000_000;

  const signals = [
    signal(now - 4),
    signal(now - 2),
    signal(now - 3),
    signal(now - 1),
  ];

  const selected = selectNewestLearningEpisodes({
    signals,
    state: {
      ...idleState,
      processed: [
        { id: episodeId(signals[1] ?? signal(now - 2)), timestamp: now - 2 },
      ],
    },
    now,
    limit: 2,
  });

  expect(selected.map((entry) => entry.timestamp)).toEqual([now - 1, now - 3]);
});

test("session learning chooses the newest pending episodes first", () => {
  const now = 1_800_000_000_000;
  const sessionId = "codex:current";
  const signals = Array.from({ length: 65 }, (_, index) => ({
    ...signal(now - index),
    sessionId,
  }));

  const selected = selectRequestedLearningEpisodes({
    signals,
    sessionKeys: new Set([fingerprint(sessionId)]),
    state: idleState,
  });

  expect(selected).toHaveLength(60);
  expect(selected[0]?.timestamp).toBe(now);
  expect(selected.at(-1)?.timestamp).toBe(now - 59);
});
