import { expect, test } from "bun:test";
import { mkdir, mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { defaultConfig, createProjectPaths } from "@shadowclone/core";
import { ingestSources, openEventIndex } from "../../eventIndex";
import { resolveRedacted } from "../redacted";
import { discoverAntigravityFiles } from "./antigravity";

const plantedSecret = ["sk", "proj", "antigravity123DEF456ghi789"].join("-");

test("returns no Antigravity transcripts when its enabled root is absent", async () => {
  const directory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-antigravity-missing-"),
  );

  expect(
    await discoverAntigravityFiles(path.join(directory, "missing")),
  ).toEqual([]);
});

test("indexes Antigravity text pointers without tool results or thinking", async () => {
  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-antigravity-"),
  );
  const paths = createProjectPaths({
    homeDirectory,
    platform: "darwin",
  });

  const logsDirectory = path.join(
    paths.antigravityBrainDirectory,
    "conversation-fixture",
    ".system_generated",
    "logs",
  );

  await mkdir(logsDirectory, { recursive: true });

  const sourcePath = path.join(logsDirectory, "transcript_full.jsonl");

  const records = [
    {
      step_index: 0,
      type: "USER_INPUT",
      status: "DONE",
      created_at: "2026-09-05T08:00:00.000Z",
      workspace: "/repo",
      content: `use ${plantedSecret}`,
    },
    {
      step_index: 1,
      type: "PLANNER_RESPONSE",
      status: "DONE",
      created_at: "2026-09-05T08:00:01.000Z",
      thinking: "private reasoning",
    },
    {
      step_index: 2,
      type: "PLANNER_RESPONSE",
      status: "DONE",
      created_at: "2026-09-05T08:00:02.000Z",
      content: "I will inspect the repository.",
      tool_calls: [{ id: "tool-1", name: "run_command" }],
    },
    {
      step_index: 3,
      type: "RUN_COMMAND",
      status: "DONE",
      created_at: "2026-09-05T08:00:03.000Z",
      tool_call_id: "tool-1",
      content: "private customer row",
    },
    {
      step_index: 4,
      type: "PLANNER_RESPONSE",
      status: "DONE",
      created_at: "2026-09-05T08:00:04.000Z",
      content: "Implemented the focused change.",
    },
    {
      step_index: 5,
      type: "CHECKPOINT",
      status: "DONE",
      created_at: "2026-09-05T08:00:05.000Z",
    },
  ];

  await Bun.write(
    sourcePath,
    `${records.map((record) => JSON.stringify(record)).join("\n")}\n`,
  );

  expect(
    await discoverAntigravityFiles(paths.antigravityBrainDirectory),
  ).toEqual([sourcePath]);

  const index = await openEventIndex(paths.indexDatabase);

  await ingestSources({
    index,
    config: {
      ...defaultConfig,
      sources: { ...defaultConfig.sources, antigravity: true },
    },
    paths,
  });

  const events = index.listEvents();

  index.close();

  expect(events.map((event) => event.kind)).toEqual([
    "user-prompt",
    "thinking",
    "tool-call",
    "tool-result",
    "assistant-text",
    "session-end",
  ]);

  const prompt = events[0];

  const promptText = prompt?.textRef
    ? await resolveRedacted({
        ref: prompt.textRef,
        roots: [path.dirname(prompt.textRef.sourcePath)],
      })
    : "";

  expect(prompt?.sessionId).toBe("conversation-fixture");
  expect(promptText).not.toContain(plantedSecret);
  expect(promptText).toContain("[redacted:llm-api-key]");
  expect(events[1]?.textRef).toBeNull();
  expect(events[2]?.textRef).toBeNull();
  expect(events[3]?.textRef).toBeNull();
  expect(events[4]?.textRef).not.toBeNull();
  expect(events[1]?.parentEventId).toBe(events[0]?.eventId);

  const databaseText = new TextDecoder().decode(
    await Bun.file(paths.indexDatabase).arrayBuffer(),
  );

  expect(databaseText).not.toContain(plantedSecret);
  expect(databaseText).not.toContain("private customer row");
});
