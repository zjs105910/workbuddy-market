import { Database } from "bun:sqlite";
import { expect, test } from "bun:test";
import { mkdir, mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { defaultConfig, createProjectPaths } from "@shadowclone/core";
import { openEventIndex } from "../../eventIndex";
import { resolveRedacted } from "../redacted";
import { observeAll } from "../index";
import type { ObservationBatch } from "../types";

const plantedSecret = ["sk", "proj", "cursor123DEF456ghi789"].join("-");

const hiddenThought = "reasoning must never be distilled";

function hex(value: string): string {
  return [...new TextEncoder().encode(value)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

test("resolves selected Cursor blob text through the redaction gate", async () => {
  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-cursor-"),
  );
  const paths = createProjectPaths({ homeDirectory, platform: "darwin" });
  const sessionDirectory = path.join(
    paths.cursorChatsDirectory,
    "workspace",
    "cursor-session",
  );

  await mkdir(sessionDirectory, { recursive: true });

  const sourcePath = path.join(sessionDirectory, "store.db");
  const database = new Database(sourcePath, { create: true, strict: true });

  database.exec(
    "CREATE TABLE blobs (id TEXT PRIMARY KEY, data BLOB); CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);",
  );

  const insertBlob = database.query<void, [string, Uint8Array]>(
    "INSERT INTO blobs (id, data) VALUES (?, ?)",
  );
  const encode = (value: unknown) =>
    new TextEncoder().encode(JSON.stringify(value));

  insertBlob.run(
    "user-blob",
    encode({
      role: "user",
      content: [
        { type: "text", text: "<user_info>internal context</user_info>" },
        {
          type: "text",
          text: `<user_query>use ${plantedSecret}</user_query>`,
        },
      ],
    }),
  );
  insertBlob.run(
    "assistant-blob",
    encode({
      role: "assistant",
      content: [
        { type: "reasoning", text: hiddenThought },
        { type: "text", text: "Implemented the focused change." },
        { type: "tool-call", toolName: "Read", toolCallId: "tool-1" },
      ],
    }),
  );
  insertBlob.run(
    "tool-blob",
    encode({ role: "tool", content: `customer row ${plantedSecret}` }),
  );
  database
    .query<void, [string]>("INSERT INTO meta (key, value) VALUES ('0', ?)")
    .run(
      hex(
        JSON.stringify({
          agentId: "cursor-session",
          createdAt: 1_788_537_600_000,
        }),
      ),
    );
  database.close();
  await Bun.write(
    path.join(sessionDirectory, "meta.json"),
    JSON.stringify({ cwd: "/repo", createdAtMs: 1_788_537_600_000 }),
  );

  const config = {
    ...defaultConfig,
    sources: { ...defaultConfig.sources, cursor: true },
  };
  const batches: ObservationBatch[] = [];

  for await (const batch of observeAll({
    config,
    paths,
    getCursor: () => null,
  })) {
    batches.push(batch);
  }

  const [batch] = batches;

  if (!batch) {
    throw new Error("Expected the Cursor fixture to be observed");
  }

  const prompt = batch.events.find((event) => event.kind === "user-prompt");
  const assistant = batch.events.find(
    (event) => event.kind === "assistant-text",
  );

  const promptText = prompt?.textRef
    ? await resolveRedacted({
        ref: prompt.textRef,
        roots: [path.dirname(prompt.textRef.sourcePath)],
      })
    : "";

  const assistantText = assistant?.textRef
    ? await resolveRedacted({
        ref: assistant.textRef,
        roots: [path.dirname(assistant.textRef.sourcePath)],
      })
    : "";

  expect(promptText).toContain("[redacted:llm-api-key]");
  expect(promptText).not.toContain(plantedSecret);
  expect(promptText).not.toContain("internal context");
  expect(assistantText).toBe("Implemented the focused change.");
  expect(assistantText).not.toContain(hiddenThought);
  expect(
    batch.events.find((event) => event.kind === "tool-result")?.textRef,
  ).toBeNull();
  expect(
    batch.events.find((event) => event.tool?.name === "Read"),
  ).toBeTruthy();

  const index = await openEventIndex(paths.indexDatabase);

  index.saveBatch(batch);

  const storedPrompt = index
    .listEvents()
    .find((event) => event.kind === "user-prompt");

  index.close();

  expect(storedPrompt?.textRef?.type).toBe("sqlite-blob");

  const indexBytes = new Uint8Array(
    await Bun.file(paths.indexDatabase).arrayBuffer(),
  );

  expect(new TextDecoder().decode(indexBytes)).not.toContain(plantedSecret);
});
