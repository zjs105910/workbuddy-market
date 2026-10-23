import { expect, test } from "bun:test";
import { mkdir, mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { defaultConfig, createProjectPaths } from "@shadowclone/core";
import { ingestSources, openEventIndex } from "../../eventIndex";

test("maps Antigravity CANCELED status to interruption event", async () => {
  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-antigravity-cancel-"),
  );
  const paths = createProjectPaths({
    homeDirectory,
    platform: "darwin",
  });

  const logsDirectory = path.join(
    paths.antigravityBrainDirectory,
    "canceled-session",
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
      content: "start working",
    },
    {
      step_index: 1,
      type: "PLANNER_RESPONSE",
      status: "CANCELED",
      created_at: "2026-09-05T08:00:01.000Z",
      content: "partial response",
    },
  ];

  await Bun.write(
    sourcePath,
    `${records.map((record) => JSON.stringify(record)).join("\n")}\n`,
  );

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
    "interruption",
  ]);
});
