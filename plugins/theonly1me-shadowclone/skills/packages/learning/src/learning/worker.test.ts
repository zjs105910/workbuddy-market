import { now, emptyRunner, fixture } from "./worker.fixtures";
import { expect, test } from "bun:test";
import path from "node:path";
import type { EngineRunner } from "@shadowclone/agents";
import { integrationFixture } from "@shadowclone/core/testing";
import { acquireLocalLock } from "@shadowclone/core";
import { runAutomaticLearning, scheduleLearning } from "./index";
import { learningInterval, readLearningState } from "./state";
import { readLatestLearningReceipt } from "./receipt";

test("automatic learning stays off without separate consent and internal runs do not schedule", async () => {
  const setup = await integrationFixture();
  let spawns = 0;

  expect(await runAutomaticLearning(setup)).toBe("disabled");
  expect(
    await scheduleLearning({
      ...setup,
      spawn: () => {
        spawns += 1;
      },
    }),
  ).toBeFalse();

  const enabled = await fixture(1);

  expect(
    await scheduleLearning({
      ...enabled,
      internalRun: true,
      spawn: () => {
        spawns += 1;
      },
    }),
  ).toBeFalse();
  expect(spawns).toBe(0);
});

test("worker serializes attempts and processes at most sixty unseen recent episodes per hour", async () => {
  const setup = await fixture(65);
  const lock = await acquireLocalLock(
    path.join(setup.paths.shadowcloneDirectory, "learning-worker.db"),
  );

  if (!lock) {
    throw new Error("Fixture lock was unavailable");
  }

  try {
    expect(await runAutomaticLearning({ ...setup, now })).toBe("busy");
  } finally {
    lock.release();
  }

  let calls = 0;
  const runner: EngineRunner = (options) => {
    calls += 1;

    return emptyRunner(options);
  };

  expect(
    await runAutomaticLearning({
      ...setup,
      now,
      runner,
      engine: "claude-code",
    }),
  ).toBe("completed");

  const firstState = await readLearningState(setup.paths);

  expect(firstState.processed).toHaveLength(60);
  expect((await readLatestLearningReceipt(setup.paths))?.episodeCount).toBe(60);
  expect((await readLatestLearningReceipt(setup.paths))?.outcome).toBe("uncertain-evidence");
  expect(firstState.processed[0]?.timestamp).toBe(now - 10_000 + 64);
  expect(firstState.processed.at(-1)?.timestamp).toBe(now - 10_000 + 5);
  expect(calls).toBe(3);
  expect(
    await runAutomaticLearning({
      ...setup,
      now: now + 1000,
      runner,
      engine: "claude-code",
    }),
  ).toBe("deferred");
  expect(
    await runAutomaticLearning({
      ...setup,
      now: now + learningInterval,
      runner,
      engine: "claude-code",
    }),
  ).toBe("completed");

  const secondState = await readLearningState(setup.paths);

  expect(secondState.processed).toHaveLength(65);
  expect(secondState.processed[60]?.timestamp).toBe(now - 10_000 + 4);
  expect(secondState.processed.at(-1)?.timestamp).toBe(now - 10_000);
  expect(calls).toBe(4);
  expect(
    await runAutomaticLearning({
      ...setup,
      now: now + 2 * learningInterval,
      runner,
      engine: "claude-code",
    }),
  ).toBe("completed");
  expect(calls).toBe(4);
});

test("the ledger keeps episodes it processed more than thirty days ago", async () => {
  const setup = await fixture(65);
  const runner: EngineRunner = (options) => emptyRunner(options);

  expect(
    await runAutomaticLearning({
      ...setup,
      now,
      runner,
      engine: "claude-code",
    }),
  ).toBe("completed");
  expect((await readLearningState(setup.paths)).processed).toHaveLength(60);

  expect(
    await runAutomaticLearning({
      ...setup,
      now: now + 31 * 24 * learningInterval,
      runner,
      engine: "claude-code",
    }),
  ).toBe("completed");

  expect((await readLearningState(setup.paths)).processed).toHaveLength(65);
});

test("a failed attempt preserves the profile and can retry at a later boundary", async () => {
  const setup = await fixture(1);
  const filePath = path.join(
    setup.paths.profileDirectory,
    "global/engineering.md",
  );
  const before = await Bun.file(filePath).text();
  const failingRunner: EngineRunner = () =>
    Promise.reject(new Error("Fixture engine failure"));

  expect(
    await runAutomaticLearning({
      ...setup,
      now,
      runner: failingRunner,
      engine: "claude-code",
    }),
  ).toBe("failed");
  expect(await Bun.file(filePath).text()).toBe(before);
  expect((await readLatestLearningReceipt(setup.paths))?.outcome).toBe("engine-failed");
  expect((await readLatestLearningReceipt(setup.paths))?.nextAction).toContain("retry");
  expect((await readLearningState(setup.paths)).processed).toEqual([]);
  expect(
    await runAutomaticLearning({
      ...setup,
      now: now + learningInterval,
      runner: emptyRunner,
      engine: "claude-code",
    }),
  ).toBe("completed");
});
