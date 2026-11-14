import { now, emptyRunner, fixture } from "./worker.fixtures";
import { expect, test } from "bun:test";
import type { EngineRunner } from "@shadowclone/agents";
import { runAutomaticLearning, scheduleLearning } from "./index";
import { readLearningState } from "./state";
import { learningSessionKey } from "@shadowclone/environment";

test("a requested session is learned even when older episodes fill the batch", async () => {
  const setup = await fixture(65);
  const prompts: string[] = [];
  const runner: EngineRunner = (options) => {
    prompts.push(options.prompt);

    return emptyRunner(options);
  };

  const sessionKeys = [
    learningSessionKey({
      agent: "claude-code",
      nativeSessionId: "session-64",
    }),
  ];

  expect(
    await runAutomaticLearning({
      ...setup,
      now,
      runner,
      engine: "claude-code",
      sessionKeys,
    }),
  ).toBe("completed");

  expect(prompts.join("\n")).toContain(
    "In session 64, always use complete variable names.",
  );
  expect((await readLearningState(setup.paths)).processed).toHaveLength(1);
});

test("a requested session bypasses the interval and learns only that session", async () => {
  const setup = await fixture(3);
  const prompts: string[] = [];
  const runner: EngineRunner = (options) => {
    prompts.push(options.prompt);

    return emptyRunner(options);
  };

  const sessionKeys = [
    learningSessionKey({
      agent: "claude-code",
      nativeSessionId: "session-1",
    }),
  ];

  expect(
    await runAutomaticLearning({
      ...setup,
      now,
      runner,
      engine: "claude-code",
      sessionKeys,
    }),
  ).toBe("completed");
  expect((await readLearningState(setup.paths)).processed).toHaveLength(1);
  expect(prompts.join("\n")).toContain(
    "In session 1, always use complete variable names.",
  );
  expect(prompts.join("\n")).not.toContain(
    "In session 0, always use complete variable names.",
  );

  let spawns = 0;

  expect(
    await scheduleLearning({
      ...setup,
      now: now + 1_000,
      sessionKeys,
      spawn: () => {
        spawns += 1;
      },
    }),
  ).toBeTrue();
  expect(spawns).toBe(1);
});
