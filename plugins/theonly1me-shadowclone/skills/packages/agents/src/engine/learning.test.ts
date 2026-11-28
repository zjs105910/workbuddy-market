import { expect, test } from "bun:test";
import type { EngineId, EngineRun, EngineRunner } from "./types";
import { createLearningExecution } from "./learning";

function result(options: {
  readonly engine: EngineId;
  readonly costUsd: number | null;
}): EngineRun {
  return {
    engine: options.engine,
    sessionId: crypto.randomUUID(),
    transcriptPath: null,
    text: "",
    structured: { rules: [] },
    costUsd: options.costUsd,
    durationMs: 1,
    turns: 1,
    isError: false,
    permissionDenials: [],
    actions: [],
    errorMessage: null,
  };
}

function learningRequest() {
  return {
    prompt: "redacted evidence",
    cwd: "/tmp",
    execution: { purpose: "learning" as const },
  };
}

test("Codex uses call limits without receiving a dollar limit", async () => {
  const budgets: (number | undefined)[] = [];
  let underlyingCalls = 0;
  const runner: EngineRunner = (options) => {
    underlyingCalls += 1;
    budgets.push(options.maxBudgetUsd);

    return Promise.resolve(result({ engine: "codex", costUsd: null }));
  };
  const execution = createLearningExecution({
    engine: "codex",
    runner,
    limits: {
      maximumCalls: 1,
      timeoutMilliseconds: 5_000,
      maximumCostUsd: 2,
    },
  });

  await execution.runner(learningRequest());

  await expect(execution.runner(learningRequest())).rejects.toThrow(
    "Learning call limit reached",
  );

  expect(underlyingCalls).toBe(1);
  expect(execution.callsUsed()).toBe(1);
  expect(budgets).toEqual([undefined]);
});

test("Claude failures are not hidden by missing cost telemetry", async () => {
  const runner: EngineRunner = () =>
    Promise.resolve({
      ...result({ engine: "claude-code", costUsd: null }),
      isError: true,
      errorMessage: "Unsupported provider option",
    });
  const execution = createLearningExecution({
    engine: "claude-code",
    runner,
    limits: {
      maximumCalls: 2,
      timeoutMilliseconds: 5_000,
      maximumCostUsd: 2,
    },
  });

  expect((await execution.runner(learningRequest())).errorMessage).toBe(
    "Unsupported provider option",
  );
  await expect(execution.runner(learningRequest())).rejects.toThrow(
    "Learning cost limit reached",
  );
});

test("the shared deadline stops a runner that does not settle", async () => {
  const runner: EngineRunner = async () => {
    await Bun.sleep(100);

    return result({ engine: "codex", costUsd: null });
  };
  const execution = createLearningExecution({
    engine: "codex",
    runner,
    limits: {
      maximumCalls: 2,
      timeoutMilliseconds: 5,
      maximumCostUsd: 2,
    },
  });

  await expect(execution.runner(learningRequest())).rejects.toThrow(
    "Learning deadline reached",
  );
  expect(execution.callsUsed()).toBe(1);
});

test("an engine without learning isolation fails before its runner", () => {
  let underlyingCalls = 0;
  const runner: EngineRunner = () => {
    underlyingCalls += 1;

    return Promise.resolve(result({ engine: "antigravity", costUsd: null }));
  };

  expect(() =>
    createLearningExecution({ engine: "antigravity", runner }),
  ).toThrow("cannot enforce the learning contract");
  expect(underlyingCalls).toBe(0);
});
