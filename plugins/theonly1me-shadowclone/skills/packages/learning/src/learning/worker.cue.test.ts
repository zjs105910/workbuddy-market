import { expect, test } from "bun:test";
import path from "node:path";
import { defaultConfig, writeConfig } from "@shadowclone/core";
import type { EngineRunner } from "@shadowclone/agents";
import { integrationFixture } from "@shadowclone/core/testing";
import { runAutomaticLearning } from "./index";
import { readLearningState } from "./state";
import { learningSessionKey } from "@shadowclone/environment";

const now = Date.parse("2026-09-26T09:00:00Z");

async function sessionFixture(message: string) {
  const setup = await integrationFixture();

  await writeConfig({
    configPath: setup.paths.configFile,
    config: {
      ...defaultConfig,
      sources: { ...defaultConfig.sources, "claude-code": true },
      distillation: { deep: true, automatic: true },
    },
  });

  const record = {
    type: "user",
    sessionId: "ended-session",
    uuid: "event-1",
    timestamp: new Date(now - 1_000).toISOString(),
    cwd: setup.cwd,
    message: { content: message },
  };

  await Bun.write(
    path.join(setup.paths.claudeProjectsDirectory, "fixture", "sessions.jsonl"),
    `${JSON.stringify(record)}\n`,
  );

  return setup;
}

function countingRunner(): {
  readonly runner: EngineRunner;
  readonly calls: () => number;
} {
  let calls = 0;

  const runner: EngineRunner = () => {
    calls += 1;

    return Promise.resolve({
      engine: "claude-code",
      sessionId: "internal",
      transcriptPath: null,
      text: "",
      structured: { existingRules: [], newRules: [], assessments: [] },
      costUsd: 0.01,
      durationMs: 1,
      turns: 1,
      isError: false,
      permissionDenials: [],
      actions: [],
      errorMessage: null,
    });
  };

  return { runner, calls: () => calls };
}

const sessionKeys = [
  learningSessionKey({
    agent: "claude-code",
    nativeSessionId: "ended-session",
  }),
];

test("an ended session without an English cue is classified and recorded", async () => {
  const setup = await sessionFixture(
    "Thanks, that looks good. Continue with the next file.",
  );
  const counter = countingRunner();

  expect(
    await runAutomaticLearning({
      ...setup,
      now,
      runner: counter.runner,
      engine: "claude-code",
      sessionKeys,
    }),
  ).toBe("completed");
  expect(counter.calls()).toBe(1);
  expect((await readLearningState(setup.paths)).processed).toHaveLength(1);
});

test("an ended session with durable steering reaches reconciliation", async () => {
  const setup = await sessionFixture(
    "Never add default exports in this repository.",
  );
  const counter = countingRunner();

  expect(
    await runAutomaticLearning({
      ...setup,
      now,
      runner: counter.runner,
      engine: "claude-code",
      sessionKeys,
    }),
  ).toBe("completed");
  expect(counter.calls()).toBeGreaterThan(0);
});
