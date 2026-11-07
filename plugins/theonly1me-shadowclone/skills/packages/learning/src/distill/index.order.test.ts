import { expect, test } from "bun:test";
import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import type { EngineRunner } from "@shadowclone/agents";
import type { IndexedEvent, CorrectionSignal } from "@shadowclone/sessions";
import { distillConcurrency, distillSignals } from "./index";

test("aggregates more than one wave of batches in source order", async () => {
  const directory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-batch-order-"),
  );
  const sourcePath = path.join(directory, "fixture.jsonl");
  const text = "Please review each edit.";

  await Bun.write(sourcePath, text);

  const textRef = {
    type: "file" as const,
    sourcePath,
    byteOffset: 0,
    byteLength: Buffer.byteLength(text),
  };

  const events: readonly IndexedEvent[] = [
    {
      id: 1,
      sourcePath,
      source: "claude-code",
      sessionId: "session-1",
      eventId: "event-1",
      parentEventId: null,
      timestamp: 1_788_537_600_000,
      cwd: "/repo",
      gitBranch: null,
      kind: "user-prompt",
      tool: null,
      isError: false,
      textRef,
    },
  ];

  const originIds = Array.from(
    { length: distillConcurrency + 1 },
    (_, batchIndex) => `github.com/org-${batchIndex}`,
  );

  const signals: readonly CorrectionSignal[] = originIds.map((originId) => ({
    kind: "interruption",
    category: "tool:Edit",
    label: "while using Edit",
    sessionId: "session-1",
    timestamp: 1_788_537_600_000,
    origin: {
      id: originId,
      directoryName: originId.replace("/", "--"),
      promotable: true,
    },
    repositoryName: null,
    textRefs: [textRef],
  }));

  const completionOrder: number[] = [];
  let callCount = 0;

  const runner: EngineRunner = async () => {
    const callNumber = ++callCount;

    await new Promise<void>((resolve) => {
      setTimeout(resolve, callNumber === 1 ? 30 : 1);
    });
    completionOrder.push(callNumber);

    return {
      engine: "codex",
      sessionId: "engine-session",
      transcriptPath: null,
      text: "",
      structured: {
        existingRules: [],
        newRules: [
          {
            title: "Review edits before continuing",
            body: "Pause after an edit and verify its direction.",
            section: "workflow",
            observed: "The user interrupted edits.",
            evidenceTokens: ["evidence-1"],
            rejectionToken: "",
          },
        ],
      },
      costUsd: 0.01,
      durationMs: 100,
      turns: 1,
      isError: false,
      permissionDenials: [],
      actions: [],
      errorMessage: null,
    };
  };

  const result = await distillSignals({
    signals,
    sourceRoots: [directory],
    runner,
    engine: "codex",
    workingDirectory: directory,
    events,
  });

  expect(callCount).toBe(originIds.length);
  expect(completionOrder[0]).not.toBe(1);
  expect(result.rules.map((rule) => rule.originDirectory)).toEqual(
    originIds.map((originId) => originId.replace("/", "--")),
  );
  expect(result.changes.map((change) => change.after.key)).toEqual(
    result.rules.map((rule) => rule.key),
  );
});
