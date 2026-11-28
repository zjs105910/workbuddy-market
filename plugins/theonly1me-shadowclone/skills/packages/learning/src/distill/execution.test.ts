import { expect, test } from "bun:test";
import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import type { EngineRunner } from "@shadowclone/agents";
import type { IndexedEvent, CorrectionSignal, OriginScope } from "@shadowclone/sessions";
import { distillSignals } from "./index";

const evidenceText = "The user asked for the smaller change.";

function origin(): OriginScope {
  return {
    id: "github.com/acme",
    directoryName: "github.com--acme--936913df4a5c268b",
    promotable: true,
  };
}

function signals(options: {
  readonly sourcePath: string;
}): readonly CorrectionSignal[] {
  return Array.from({ length: 21 }, (_, signalIndex) => ({
    kind: "interruption" as const,
    category: "tool:Edit",
    label: "while using Edit",
    sessionId: `session-${signalIndex}`,
    timestamp: 1_788_537_600_000 + signalIndex,
    origin: origin(),
    repositoryName: null,
    textRefs: [
      {
        type: "file" as const,
        sourcePath: options.sourcePath,
        byteOffset: 0,
        byteLength: Buffer.byteLength(evidenceText),
      },
    ],
  }));
}

function event(options: { readonly sourcePath: string }): IndexedEvent {
  return {
    id: 1,
    sourcePath: options.sourcePath,
    source: "claude-code",
    sessionId: "session-0",
    eventId: "event-1",
    parentEventId: null,
    timestamp: 1_788_537_600_000,
    cwd: "/repo",
    gitBranch: null,
    kind: "user-prompt",
    tool: null,
    isError: false,
    textRef: {
      type: "file",
      sourcePath: options.sourcePath,
      byteOffset: 0,
      byteLength: Buffer.byteLength(evidenceText),
    },
  };
}

test("one learning allowance stops before a second extraction batch", async () => {
  const directory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-learning-limit-"),
  );
  const sourcePath = path.join(directory, "evidence.txt");

  await Bun.write(sourcePath, evidenceText);

  const budgets: (number | undefined)[] = [];
  let calls = 0;

  const runner: EngineRunner = (options) => {
    calls += 1;
    budgets.push(options.maxBudgetUsd);

    return Promise.resolve({
      engine: "codex",
      sessionId: `engine-${calls}`,
      transcriptPath: null,
      text: "",
      structured: {
        existingRules: [],
        newRules: [
          {
            title: "Prefer the smaller change",
            body: "Choose the smallest change that solves the problem.",
            section: "workflow",
            observed: "The user asked for a smaller change.",
            evidenceTokens: ["evidence-1"],
            rejectionToken: "",
          },
        ],
      },
      costUsd: null,
      durationMs: 10,
      turns: 1,
      isError: false,
      permissionDenials: [],
      actions: [],
      errorMessage: null,
    });
  };

  await expect(
    distillSignals({
      signals: signals({ sourcePath }),
      events: [event({ sourcePath })],
      runner,
      engine: "codex",
      limits: {
        maximumCalls: 1,
        timeoutMilliseconds: 5_000,
        maximumCostUsd: 2,
      },
      workingDirectory: directory,
      sourceRoots: [directory],
      checkpointDirectory: path.join(directory, "checkpoints"),
    }),
  ).rejects.toThrow("Learning call limit reached");

  expect(calls).toBe(1);
  expect(budgets).toEqual([undefined]);
});
