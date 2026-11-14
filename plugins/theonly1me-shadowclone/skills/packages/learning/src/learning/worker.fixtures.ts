import path from "node:path";
import { defaultConfig, writeConfig } from "@shadowclone/core";
import type { EngineRunner } from "@shadowclone/agents";
import { integrationFixture } from "@shadowclone/core/testing";

export const now = Date.parse("2026-09-11T09:00:00Z");

export const emptyRunner: EngineRunner = () =>
  Promise.resolve({
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

export async function fixture(sessionCount: number) {
  const setup = await integrationFixture();

  await writeConfig({
    configPath: setup.paths.configFile,
    config: {
      ...defaultConfig,
      sources: { ...defaultConfig.sources, "claude-code": true },
      distillation: { deep: true, automatic: true },
    },
  });

  const records = Array.from({ length: sessionCount }, (_, position) => ({
    type: "user",
    sessionId: `session-${position}`,
    uuid: `event-${position}`,
    timestamp: new Date(now - 10_000 + position).toISOString(),
    cwd: setup.cwd,
    message: {
      content: `In session ${position}, always use complete variable names.`,
    },
  }));

  await Bun.write(
    path.join(setup.paths.claudeProjectsDirectory, "fixture", "sessions.jsonl"),
    `${records.map((record) => JSON.stringify(record)).join("\n")}\n`,
  );

  return setup;
}
