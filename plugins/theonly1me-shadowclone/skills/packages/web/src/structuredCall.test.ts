import { expect, test } from "bun:test";
import { z } from "zod";
import type { EngineRun } from "@shadowclone/agents";
import { generationResult } from "./fixtures";
import { structuredCall } from "./structuredCall";

function call(options: { readonly runner: () => Promise<EngineRun>; readonly timeoutMilliseconds: number }) {
  return structuredCall({
    connection: { engine: "claude-code", model: "haiku", runner: options.runner },
    prompt: "Name a synthetic build.",
    schema: z.strictObject({ title: z.string() }),
    limits: { maximumCalls: 1, timeoutMilliseconds: options.timeoutMilliseconds, maximumCostUsd: 0.05 },
    cwd: "/tmp",
    signal: new AbortController().signal,
    task: "name the build",
  });
}

test("a call that runs past its deadline names the action and the limit", async () => {
  await expect(call({ runner: () => new Promise<EngineRun>(() => undefined), timeoutMilliseconds: 20 })).rejects.toThrow(
    "claude-code using haiku did not name the build within 0.02 seconds.",
  );
});

test("a call that spends past its cost limit names the action and the limit", async () => {
  await expect(
    call({ runner: async () => ({ ...generationResult({ title: "Synthetic" }), costUsd: 0.07 }), timeoutMilliseconds: 1_000 }),
  ).rejects.toThrow("claude-code using haiku reached the $0.05 cost limit before it could name the build.");
});
