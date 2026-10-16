import { expect, test } from "bun:test";
import { mkdir, mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import {
  defaultConfig,
  setSourceEnabled,
  writeConfig,
  createProjectPaths,
} from "@shadowclone/core";
import type { EngineRunner } from "@shadowclone/agents";
import { learn } from "./learn";

test("learn --dry-run does not create profile directory or write database", async () => {
  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-dry-"),
  );
  const paths = createProjectPaths({ homeDirectory, platform: "darwin" });

  await mkdir(paths.claudeProjectsDirectory, { recursive: true });

  const config = setSourceEnabled({
    config: defaultConfig,
    source: "claude-code",
    enabled: true,
  });

  await writeConfig({ config, configPath: paths.configFile });

  await learn({
    configPath: paths.configFile,
    paths,
    dryRun: true,
    managedConfigPath: null,
  });

  expect(await Bun.file(paths.profileDirectory).exists()).toBeFalse();
  expect(await Bun.file(paths.indexDatabase).exists()).toBeFalse();
});

test("learn --deep --dry-run reconciles without writing learning state", async () => {
  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-deep-dry-"),
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
      cwd: "/repo",
      message: {
        id: "message-1",
        content: [{ type: "tool_use", id: "tool-1", name: "AskUserQuestion" }],
      },
    },
    {
      type: "user",
      sessionId: "session",
      uuid: "event-2",
      timestamp: "2026-09-09T08:01:00.000Z",
      cwd: "/repo",
      message: { id: "message-2", content: "Choose the smaller change" },
    },
  ];

  await Bun.write(
    path.join(transcriptDirectory, "session.jsonl"),
    `${records.map((record) => JSON.stringify(record)).join("\n")}\n`,
  );

  const config = setSourceEnabled({
    config: { ...defaultConfig, distillation: { deep: true } },
    source: "claude-code",
    enabled: true,
  });

  await writeConfig({ config, configPath: paths.configFile });

  let calls = 0;
  let confirmations = 0;
  const runner: EngineRunner = () => {
    calls += 1;

    return Promise.resolve({
      engine: "claude-code",
      sessionId: "engine-session",
      transcriptPath: null,
      text: "",
      structured: {
        existingRules: [],
        newRules: [
          {
            title: "Prefer small changes",
            body: "Choose the smallest change that satisfies the request.",
            section: "workflow",
            observed: "The user selected the smaller change.",
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

  await learn({
    configPath: paths.configFile,
    paths,
    deep: true,
    dryRun: true,
    runner,
    engine: "claude-code",
    confirm: () => {
      confirmations += 1;

      return true;
    },
    writeLine: () => {},
    managedConfigPath: null,
  });

  expect(calls).toBe(1);
  expect(confirmations).toBe(0);
  expect(await Bun.file(paths.indexDatabase).exists()).toBeFalse();
  expect(await Bun.file(paths.profileDirectory).exists()).toBeFalse();
  expect(await Bun.file(paths.distillDirectory).exists()).toBeFalse();
});
