import { expect, test } from "bun:test";
import { mkdir, mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { resolveRedacted } from "../redacted";
import { discoverCodexFiles, observeCodexFile } from "./codex";

const plantedSecret = ["sk", "proj", "codex123DEF456ghi789"].join("-");

test("reads one Codex event view and keeps tool results text-free", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "shadowclone-codex-"));
  const sessionDirectory = path.join(directory, "2026", "09", "05");

  await mkdir(sessionDirectory, { recursive: true });

  const sourcePath = path.join(sessionDirectory, "rollout-fixture.jsonl");

  const records = [
    {
      timestamp: "2026-09-05T08:00:00.000Z",
      type: "session_meta",
      payload: { id: "codex-session", cwd: "/repo", git: { branch: "main" } },
    },
    {
      timestamp: "2026-09-05T08:00:01.000Z",
      type: "event_msg",
      payload: { type: "user_message", message: `use ${plantedSecret}` },
    },
    {
      timestamp: "2026-09-05T08:00:01.000Z",
      type: "response_item",
      payload: {
        type: "message",
        role: "user",
        content: [{ type: "input_text", text: `use ${plantedSecret}` }],
      },
    },
    {
      timestamp: "2026-09-05T08:00:02.000Z",
      type: "response_item",
      payload: { type: "function_call", name: "shell", call_id: "call-1" },
    },
    {
      timestamp: "2026-09-05T08:00:03.000Z",
      type: "response_item",
      payload: {
        type: "function_call_output",
        call_id: "call-1",
        output: "private customer row",
      },
    },
    {
      timestamp: "2026-09-05T08:00:04.000Z",
      type: "event_msg",
      payload: { type: "task_complete" },
    },
  ];

  await Bun.write(
    sourcePath,
    `${records.map((record) => JSON.stringify(record)).join("\n")}\n`,
  );

  expect(await discoverCodexFiles(directory)).toEqual([sourcePath]);

  const batch = await observeCodexFile({ sourcePath, cursor: null });
  const prompts =
    batch?.events.filter((event) => event.kind === "user-prompt") ?? [];

  const text = prompts[0]?.textRef
    ? await resolveRedacted({
        ref: prompts[0].textRef,
        roots: [path.dirname(prompts[0].textRef.sourcePath)],
      })
    : "";

  expect(prompts).toHaveLength(1);
  expect(text).not.toContain(plantedSecret);
  expect(text).toContain("[redacted:llm-api-key]");
  expect(
    batch?.events.find((event) => event.kind === "tool-result")?.textRef,
  ).toBeNull();
  expect(batch?.events.at(-1)?.kind).toBe("session-end");
  expect(batch?.events[1]?.parentEventId).toBe(batch?.events[0]?.eventId);

  const appended = {
    timestamp: "2026-09-05T08:00:05.000Z",
    type: "response_item",
    payload: {
      type: "message",
      role: "assistant",
      content: [{ type: "output_text", text: "Done" }],
    },
  };

  await Bun.write(
    sourcePath,
    `${await Bun.file(sourcePath).text()}${JSON.stringify(appended)}\n`,
  );

  const incremental = batch
    ? await observeCodexFile({ sourcePath, cursor: batch.cursor })
    : null;

  expect(incremental?.events[0]?.sessionId).toBe("codex-session");
  expect(incremental?.events[0]?.cwd).toBe("/repo");
});
