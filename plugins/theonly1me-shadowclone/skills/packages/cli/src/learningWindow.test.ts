import { expect, test } from "bun:test";
import type { CorrectionSignal } from "@shadowclone/sessions";
import { episodeId, type LearningState } from "@shadowclone/learning";
import { selectManualLearningWindow } from "./learningWindow";

const idleState: LearningState = {
  lastAttemptAt: null,
  lastCompletedAt: null,
  status: "idle",
  processed: [],
};

function signal(options: {
  readonly index: number;
  readonly timestamp: number;
  readonly sharedOrigin?: boolean;
}): CorrectionSignal {
  const suffix = options.sharedOrigin ? "shared" : options.index.toString();

  return {
    kind: "interruption",
    category: "tool:Edit",
    label: "while using Edit",
    sessionId: `session-${options.index}`,
    timestamp: options.timestamp,
    origin: {
      id: `github.com/${suffix}`,
      directoryName: `github.com--${suffix}`,
      promotable: true,
    },
    repositoryName: null,
    textRefs: [],
  };
}

test("manual learning reserves calls while starting from the newest batches", () => {
  const now = 1_800_000_000_000;
  const window = selectManualLearningWindow({
    signals: Array.from({ length: 12 }, (_, index) =>
      signal({
        index,
        timestamp: now - 12 + index,
      }),
    ),
    state: idleState,
    now,
  });

  expect(window.batches).toHaveLength(10);
  expect(window.signals.map((entry) => entry.sessionId)).toEqual(
    Array.from({ length: 10 }, (_, index) => `session-${11 - index}`),
  );
});

test("manual learning considers at most sixty pending episodes", () => {
  const now = 1_800_000_000_000;
  const window = selectManualLearningWindow({
    signals: Array.from({ length: 65 }, (_, index) =>
      signal({
        index,
        timestamp: now - index,
        sharedOrigin: true,
      }),
    ),
    state: idleState,
    now,
  });

  expect(window.signals).toHaveLength(60);
  expect(window.batches).toHaveLength(3);
  expect(window.signals[0]?.timestamp).toBe(now);
  expect(window.signals.at(-1)?.timestamp).toBe(now - 59);
});

test("manual learning reaches episodes older than the former thirty day horizon", () => {
  const now = 1_800_000_000_000;
  const ancient = now - 300 * 24 * 60 * 60 * 1_000;
  const window = selectManualLearningWindow({
    signals: [signal({ index: 0, timestamp: ancient, sharedOrigin: true })],
    state: idleState,
    now,
  });

  expect(window.signals.map((entry) => entry.timestamp)).toEqual([ancient]);
});

test("manual learning skips episodes already recorded in the ledger", () => {
  const now = 1_800_000_000_000;
  const signals = Array.from({ length: 3 }, (_, index) =>
    signal({
      index,
      timestamp: now - 3 + index,
      sharedOrigin: true,
    }),
  );
  const covered = selectManualLearningWindow({
    signals,
    state: idleState,
    now,
  });
  const state: LearningState = {
    ...idleState,
    processed: covered.signals.slice(0, 2).map((entry) => ({
      id: episodeId(entry),
      timestamp: entry.timestamp,
    })),
  };

  const window = selectManualLearningWindow({ signals, state, now });

  expect(window.signals.map((entry) => entry.sessionId)).toEqual(["session-0"]);
});

test("a catch-up run scales the episode ceiling with the call ceiling", () => {
  const now = 1_800_000_000_000;
  const signals = Array.from({ length: 900 }, (_, index) =>
    signal({
      index,
      timestamp: now - 900 + index,
      sharedOrigin: true,
    }),
  );

  const standard = selectManualLearningWindow({
    signals,
    state: idleState,
    now,
  });
  const catchUp = selectManualLearningWindow({
    signals,
    state: idleState,
    now,
    maximumCalls: 40,
  });

  expect(standard.signals).toHaveLength(60);
  expect(standard.signals[0]?.sessionId).toBe("session-899");
  expect(standard.signals.at(-1)?.sessionId).toBe("session-840");
  expect(catchUp.signals).toHaveLength(400);
  expect(catchUp.signals[0]?.sessionId).toBe("session-899");
  expect(catchUp.signals.at(-1)?.sessionId).toBe("session-500");
  expect(catchUp.batches).toHaveLength(20);
});
