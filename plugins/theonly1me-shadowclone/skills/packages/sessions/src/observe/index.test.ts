import { expect, test } from "bun:test";
import { mkdir, mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { defaultConfig, createProjectPaths, type ProjectPaths } from "@shadowclone/core";
import { resolveRedacted } from "./redacted";
import { observeAll } from "./index";
import type { AgentEvent } from "./types";

const plantedSecret = ["sk", "proj", "abc123DEF456ghi789JKL"].join("-");

async function createClaudeFixture(): Promise<{
  readonly homeDirectory: string;
  readonly sourcePath: string;
}> {
  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-observe-"),
  );

  const projectsDirectory = path.join(
    homeDirectory,
    ".claude",
    "projects",
    "fixture",
  );

  await mkdir(projectsDirectory, { recursive: true });

  const sourcePath = path.join(projectsDirectory, "session-1.jsonl");

  const records = [
    {
      type: "user",
      sessionId: "session-1",
      uuid: "user-1",
      timestamp: "2026-09-05T08:00:00.000Z",
      cwd: "/repo",
      message: { id: "message-1", content: `use ${plantedSecret}` },
    },
    {
      type: "assistant",
      sessionId: "session-1",
      uuid: "assistant-1",
      requestId: "request-1",
      message: {
        id: "message-2",
        content: [{ type: "tool_use", id: "tool-1", name: "Read" }],
      },
    },
    {
      type: "user",
      sessionId: "session-1",
      uuid: "result-1",
      message: {
        id: "message-3",
        content: [{ type: "tool_result", content: "private customer row" }],
      },
    },
    {
      type: "assistant",
      sessionId: "session-1",
      uuid: "assistant-2",
      message: {
        id: "message-4",
        content: [
          {
            type: "tool_use",
            id: "tool-2",
            name: "AskUserQuestion",
            input: { question: "Which scope?", options: ["small", "large"] },
          },
        ],
      },
    },
    {
      type: "user",
      sessionId: "session-1",
      uuid: "answer-1",
      message: {
        id: "message-5",
        content: [
          {
            type: "tool_result",
            tool_use_id: "tool-2",
            content: "User has answered your questions: small",
          },
        ],
      },
    },
    {
      type: "result",
      session_id: "session-1",
      uuid: "terminal-1",
      is_error: false,
    },
  ];

  await Bun.write(
    sourcePath,
    `${records.map((record) => JSON.stringify(record)).join("\n")}\n`,
  );

  return { homeDirectory, sourcePath };
}

test("keeps captured text behind resolveRedacted", async () => {
  const fixture = await createClaudeFixture();
  const paths = createProjectPaths({
    homeDirectory: fixture.homeDirectory,
    platform: "darwin",
  });
  const config = {
    ...defaultConfig,
    sources: { ...defaultConfig.sources, "claude-code": true },
  };
  const events: AgentEvent[] = [];

  for await (const batch of observeAll({
    config,
    paths,
    getCursor: () => null,
  })) {
    events.push(...batch.events);
  }

  const prompt = events.find((event) => event.kind === "user-prompt");

  expect(prompt?.textRef).not.toBeNull();

  const text = prompt?.textRef
    ? await resolveRedacted({
        ref: prompt.textRef,
        roots: [path.dirname(prompt.textRef.sourcePath)],
      })
    : "";

  expect(text).not.toContain(plantedSecret);
  expect(text).toContain("[redacted:llm-api-key]");

  const toolResult = events.find((event) => event.kind === "tool-result");

  expect(toolResult?.textRef).toBeNull();

  const question = events.find((event) => event.kind === "question-asked");
  const answer = events.find((event) => event.kind === "question-answered");

  expect(question?.textRef).not.toBeNull();
  expect(answer?.textRef).toBeNull();
  expect(events.some((event) => event.kind === "session-end")).toBeTrue();
});

test("does not touch paths for disabled sources", async () => {
  const basePaths = createProjectPaths({
    homeDirectory: "/path/that/must/not/be/read",
    platform: "linux",
  });

  const paths: ProjectPaths = {
    ...basePaths,
    get antigravityBrainDirectory(): string {
      throw new Error("Disabled Antigravity path was accessed");
    },
    get codexSessionsDirectory(): string {
      throw new Error("Disabled Codex path was accessed");
    },
    get cursorChatsDirectory(): string {
      throw new Error("Disabled Cursor path was accessed");
    },
  };

  let cursorLookups = 0;

  for await (const batch of observeAll({
    config: defaultConfig,
    paths,
    getCursor: () => {
      cursorLookups += 1;

      return null;
    },
  })) {
    expect(batch).toBeUndefined();
  }

  expect(cursorLookups).toBe(0);
});
