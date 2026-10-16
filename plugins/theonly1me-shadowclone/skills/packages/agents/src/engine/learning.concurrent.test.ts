import { expect, test } from "bun:test";
import { createLearningExecution } from "./learning";
import type { EngineRun, EngineRunner } from "./types";

const request = {
  prompt: "synthetic guidance",
  cwd: "/tmp",
  execution: { purpose: "learning" as const },
};
const limits = {
  maximumCalls: 8,
  timeoutMilliseconds: 1_000,
  maximumCostUsd: 2,
};

function result(costUsd: number | null): EngineRun {
  return {
    engine: "claude-code",
    sessionId: "synthetic",
    transcriptPath: null,
    text: "",
    structured: null,
    costUsd,
    durationMs: 1,
    turns: 1,
    isError: false,
    permissionDenials: [],
    actions: [],
    errorMessage: null,
  };
}

test("eight concurrent requests share one dollar allowance at dispatch", async () => {
  const allowances: number[] = [];
  let spending = 0;
  let active = 0;
  let maximumActive = 0;

  const runner: EngineRunner = async (options) => {
    const allowance = options.maxBudgetUsd ?? 0;

    allowances.push(allowance);
    active += 1;
    maximumActive = Math.max(maximumActive, active);
    await Bun.sleep(5);

    const cost = Math.min(0.75, allowance);

    spending += cost;
    active -= 1;

    return result(cost);
  };

  const execution = createLearningExecution({
    engine: "claude-code",
    runner,
    limits,
  });

  const outcomes = await Promise.allSettled(
    Array.from({ length: 8 }, () => execution.runner(request)),
  );

  expect(spending).toBe(2);
  expect(allowances).toEqual([2, 1.25, 0.5]);
  expect(maximumActive).toBe(1);
  expect(execution.callsUsed()).toBe(3);
  expect(
    outcomes.filter((outcome) => outcome.status === "fulfilled"),
  ).toHaveLength(3);
});

for (const cost of [null, NaN, -1, Infinity]) {
  test(`unknown or invalid successful cost seals queued spending: ${cost}`, async () => {
    let calls = 0;
    const execution = createLearningExecution({
      engine: "claude-code",
      limits,
      runner: async () => {
        calls += 1;

        return result(cost);
      },
    });
    const outcomes = await Promise.allSettled([
      execution.runner(request),
      execution.runner(request),
    ]);

    expect(calls).toBe(1);
    expect(outcomes.every((outcome) => outcome.status === "rejected")).toBe(
      true,
    );
  });
}

test("a thrown provider failure cannot renew a queued allowance", async () => {
  let calls = 0;

  const execution = createLearningExecution({
    engine: "claude-code",
    limits,
    runner: async () => {
      calls += 1;

      throw new Error("synthetic provider failure");
    },
  });

  const outcomes = await Promise.allSettled([
    execution.runner(request),
    execution.runner(request),
  ]);

  expect(calls).toBe(1);
  expect(outcomes.every((outcome) => outcome.status === "rejected")).toBe(true);
});

test("queued requests retain the original deadline", async () => {
  let calls = 0;

  const execution = createLearningExecution({
    engine: "claude-code",
    limits: { ...limits, timeoutMilliseconds: 10 },
    runner: async () => {
      calls += 1;
      await Bun.sleep(30);

      return result(0);
    },
  });

  await Promise.allSettled([
    execution.runner(request),
    execution.runner(request),
  ]);

  expect(calls).toBe(1);
});

test("zero cost is valid and queued calls still respect the call limit", async () => {
  let calls = 0;

  const execution = createLearningExecution({
    engine: "claude-code",
    limits: { ...limits, maximumCalls: 2 },
    runner: async () => {
      calls += 1;

      return result(0);
    },
  });

  await Promise.allSettled(
    Array.from({ length: 5 }, () => execution.runner(request)),
  );

  expect(calls).toBe(2);
});
