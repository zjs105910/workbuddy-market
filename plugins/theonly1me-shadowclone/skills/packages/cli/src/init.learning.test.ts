import { expect, test } from "bun:test";
import { mkdir, mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import type { EngineRunner } from "@shadowclone/agents";
import { readLearningState } from "@shadowclone/learning";
import { createProjectPaths } from "@shadowclone/core";
import { initialize } from "./init";

test("default setup processes recent steering before the next agent session", async () => {
  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-init-learning-"),
  );
  const paths = createProjectPaths({ homeDirectory, platform: "darwin" });
  const transcriptDirectory = path.join(
    paths.claudeProjectsDirectory,
    "fixture",
  );

  await mkdir(transcriptDirectory, { recursive: true });

  const records = [
    {
      type: "assistant",
      sessionId: "session",
      uuid: "event-1",
      timestamp: "2026-09-09T08:00:00.000Z",
      cwd: homeDirectory,
      message: {
        id: "message-1",
        content: [
          {
            type: "tool_use",
            id: "tool-1",
            name: "AskUserQuestion",
            input: { question: "Which scope?", options: ["small", "large"] },
          },
        ],
      },
    },
    {
      type: "user",
      sessionId: "session",
      uuid: "event-2",
      timestamp: "2026-09-09T08:01:00.000Z",
      cwd: homeDirectory,
      message: { id: "message-2", content: "Use the small scope" },
    },
  ];

  await Bun.write(
    path.join(transcriptDirectory, "session.jsonl"),
    `${records.map((record) => JSON.stringify(record)).join("\n")}\n`,
  );

  let engineRuns = 0;
  const runner: EngineRunner = () => {
    engineRuns += 1;

    return Promise.resolve({
      engine: "claude-code",
      sessionId: "deep-session",
      transcriptPath: null,
      text: "",
      structured: {
        existingRules: [],
        newRules: [
          {
            title: "Use the small scope",
            body: "Choose the small scope when the user asks for it.",
            section: "workflow",
            observed: "The user chose the small scope.",
            evidenceTokens: ["evidence-1"],
            rejectionToken: "",
          },
        ],
      },
      costUsd: 0.01,
      durationMs: 10,
      turns: 1,
      isError: false,
      permissionDenials: [],
      actions: [],
      errorMessage: null,
    });
  };

  await initialize({
    paths,
    workingDirectory: homeDirectory,
    presence: {
      hasRepositoryGuidance: false,
      presentCaptureSources: new Set(["claude-code"]),
    },
    agents: [],
    ask: (question) => !question.startsWith("Keep your skills"),
    runner,
    engine: "claude-code",
    now: Date.parse("2026-09-13T00:00:00.000Z"),
    readRemote: async () => "git@github.com:acme/repo.git",
    managedConfigPath: null,
    writeLine: () => {},
  });

  expect(engineRuns).toBe(1);
  expect((await readLearningState(paths)).processed).toHaveLength(1);
});

test("setup completes when the learning call budget is reached", async () => {
  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-init-learning-"),
  );
  const paths = createProjectPaths({ homeDirectory, platform: "darwin" });
  const transcriptDirectory = path.join(
    paths.claudeProjectsDirectory,
    "fixture",
  );

  await mkdir(transcriptDirectory, { recursive: true });

  const records = [
    {
      type: "assistant",
      sessionId: "session",
      uuid: "event-1",
      timestamp: "2026-09-09T08:00:00.000Z",
      cwd: homeDirectory,
      message: {
        id: "message-1",
        content: [
          {
            type: "tool_use",
            id: "tool-1",
            name: "AskUserQuestion",
            input: { question: "Which scope?", options: ["small", "large"] },
          },
        ],
      },
    },
    {
      type: "user",
      sessionId: "session",
      uuid: "event-2",
      timestamp: "2026-09-09T08:01:00.000Z",
      cwd: homeDirectory,
      message: { id: "message-2", content: "Use the small scope" },
    },
  ];

  await Bun.write(
    path.join(transcriptDirectory, "session.jsonl"),
    `${records.map((record) => JSON.stringify(record)).join("\n")}\n`,
  );

  const output: string[] = [];

  await initialize({
    paths,
    workingDirectory: homeDirectory,
    presence: {
      hasRepositoryGuidance: false,
      presentCaptureSources: new Set(["claude-code"]),
    },
    agents: [],
    ask: (question) => !question.startsWith("Keep your skills"),
    runner: () => {
      throw new Error("Learning call limit reached");
    },
    engine: "claude-code",
    now: Date.parse("2026-09-13T00:00:00.000Z"),
    readRemote: async () => "git@github.com:acme/repo.git",
    managedConfigPath: null,
    writeLine: (line) => output.push(line),
  });

  expect(
    output.some((line) => line.includes("12 total calls and 90 seconds")),
  ).toBeTrue();
  expect(output).toContain(
    "Learning reached its setup budget; background learning will continue.",
  );
  expect((await readLearningState(paths)).processed).toHaveLength(0);
});
