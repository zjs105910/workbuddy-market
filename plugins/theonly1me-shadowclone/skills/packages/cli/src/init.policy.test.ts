import { expect, test } from "bun:test";
import { mkdir, mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import {
  defaultConfig,
  defaultManagedPolicy,
  readConfig,
  setSourceEnabled,
  createProjectPaths,
} from "@shadowclone/core";
import { ingestSources, openEventIndex } from "@shadowclone/sessions";
import { initialize } from "./init";

test("first setup learning obeys managed source restrictions", async () => {
  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-init-policy-"),
  );
  const paths = createProjectPaths({ homeDirectory, platform: "darwin" });
  const transcriptDirectory = path.join(
    paths.claudeProjectsDirectory,
    "fixture",
  );

  await mkdir(transcriptDirectory, { recursive: true });
  await Bun.write(
    path.join(transcriptDirectory, "session.jsonl"),
    `${JSON.stringify({
      type: "user",
      sessionId: "session",
      uuid: "event-1",
      timestamp: "2026-09-09T08:00:00.000Z",
      cwd: homeDirectory,
      message: { id: "message-1", content: "Use the small scope" },
    })}\n`,
  );

  let modelCalls = 0;

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
      modelCalls += 1;

      throw new Error("Blocked capture cannot reach the model");
    },
    engine: "claude-code",
    now: Date.parse("2026-09-13T00:00:00.000Z"),
    managedPolicy: {
      ...defaultManagedPolicy,
      allowedSources: defaultManagedPolicy.allowedSources.filter(
        (source) => source !== "claude-code",
      ),
    },
    managedConfigPath: null,
    writeLine: () => {},
  });

  expect(
    (await readConfig({ configPath: paths.configFile })).sources["claude-code"],
  ).toBeTrue();

  const index = await openEventIndex(paths.indexDatabase);

  expect(index.countEvents()).toBe(0);

  index.close();

  expect(modelCalls).toBe(0);
});

test("first setup learning excludes indexed events after policy or consent revokes their source", async () => {
  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-init-policy-"),
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

  const index = await openEventIndex(paths.indexDatabase);

  await ingestSources({
    index,
    paths,
    config: setSourceEnabled({
      config: defaultConfig,
      source: "claude-code",
      enabled: true,
    }),
  });

  expect(index.countEvents()).toBe(2);

  index.close();

  let modelCalls = 0;

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
      modelCalls += 1;

      throw new Error("Revoked capture cannot reach the model");
    },
    engine: "claude-code",
    now: Date.parse("2026-09-13T00:00:00.000Z"),
    managedPolicy: {
      ...defaultManagedPolicy,
      allowedSources: defaultManagedPolicy.allowedSources.filter(
        (source) => source !== "claude-code",
      ),
    },
    managedConfigPath: null,
    writeLine: () => {},
  });

  expect(modelCalls).toBe(0);

  await initialize({
    paths,
    workingDirectory: homeDirectory,
    presence: {
      hasRepositoryGuidance: false,
      presentCaptureSources: new Set(["claude-code"]),
    },
    agents: [],
    consent: { learn: false, skills: false, background: false },
    runner: () => {
      modelCalls += 1;

      throw new Error("Declined capture cannot reach the model");
    },
    engine: "claude-code",
    now: Date.parse("2026-09-13T00:00:00.000Z"),
    managedConfigPath: null,
    writeLine: () => {},
  });

  expect(modelCalls).toBe(0);
});
