import { expect, test } from "bun:test";
import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import type { EngineRun, EngineRunner } from "@shadowclone/agents";
import type { IndexedEvent, CorrectionSignal, OriginScope } from "@shadowclone/sessions";
import { distillSignals, groupDistillBatches } from "./index";

const plantedSecret = ["sk", "proj", "distillSecret123456789"].join("-");

function origin(id: string): OriginScope {
  return { id, directoryName: id.replace("/", "--"), promotable: true };
}

function signal(options: {
  readonly sourcePath: string;
  readonly origin: OriginScope;
}): CorrectionSignal {
  return {
    kind: "interruption",
    category: "tool:Edit",
    label: "while using Edit",
    sessionId: "session-1",
    timestamp: 1_788_537_600_000,
    origin: options.origin,
    repositoryName: null,
    textRefs: [
      {
        type: "file",
        sourcePath: options.sourcePath,
        byteOffset: 0,
        byteLength: Buffer.byteLength(plantedSecret),
      },
    ],
  };
}

function successfulRun(): EngineRun {
  return {
    engine: "claude-code",
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
          observed: "The user repeatedly interrupted edits.",
          evidenceTokens: ["evidence-1", "evidence-2"],
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
}

function indexedPrompt(options: {
  readonly sourcePath: string;
  readonly sessionId?: string;
  readonly byteLength?: number;
}): IndexedEvent {
  const byteLength = options.byteLength ?? Buffer.byteLength(plantedSecret);

  return {
    id: 1,
    sourcePath: options.sourcePath,
    source: "claude-code",
    sessionId: options.sessionId ?? "session-1",
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
      byteLength,
    },
  };
}

test("separates repository scopes before resolving any pointer", () => {
  const first = signal({
    sourcePath: "/must/not/be/read-one",
    origin: origin("github.com/one"),
  });
  const second = signal({
    sourcePath: "/must/not/be/read-two",
    origin: origin("github.com/two"),
  });

  expect(groupDistillBatches({ signals: [first, second] })).toHaveLength(2);
});

test("redacts excerpts before the engine and resumes from checkpoints", async () => {
  const directory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-distill-"),
  );
  const sourcePath = path.join(directory, "fixture.jsonl");

  await Bun.write(sourcePath, plantedSecret);

  const signals = [signal({ sourcePath, origin: origin("github.com/acme") })];
  const prompts: string[] = [];
  const runner: EngineRunner = (options) => {
    prompts.push(options.prompt);

    return Promise.resolve(successfulRun());
  };

  const options = {
    signals,
    runner,
    engine: "claude-code" as const,
    workingDirectory: directory,
    sourceRoots: [directory],
    checkpointDirectory: path.join(directory, "checkpoints"),
    events: [indexedPrompt({ sourcePath })],
  };

  const first = await distillSignals(options);
  const second = await distillSignals(options);

  expect(prompts).toHaveLength(1);
  expect(prompts[0]).not.toContain(plantedSecret);
  expect(prompts[0]).toContain("[redacted:llm-api-key]");
  expect(first.engineRuns).toBe(1);
  expect(second.engineRuns).toBe(0);
  expect(second.rules).toEqual(first.rules);
});

test("records independent supporting evidence without a confidence score", async () => {
  const directory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-distill-conf-"),
  );
  const sourcePath = path.join(directory, "fixture.jsonl");

  await Bun.write(sourcePath, "user edited code");

  const orig = origin("github.com/acme");

  const makeSignal = (
    sessionId: string,
    timestamp: number,
  ): CorrectionSignal => ({
    kind: "interruption",
    category: "tool:Edit",
    label: "while using Edit",
    sessionId,
    timestamp,
    origin: orig,
    repositoryName: null,
    textRefs: [{ type: "file", sourcePath, byteOffset: 0, byteLength: 16 }],
  });

  const signals = [
    makeSignal("session-1", 1_788_537_600_000),
    makeSignal("session-2", 1_788_537_700_000),
  ];
  const runner: EngineRunner = () => Promise.resolve(successfulRun());

  const options = {
    signals,
    runner,
    engine: "claude-code" as const,
    workingDirectory: directory,
    sourceRoots: [directory],
    checkpointDirectory: path.join(directory, "checkpoints"),
    events: [
      indexedPrompt({ sourcePath, sessionId: "session-1", byteLength: 16 }),
      indexedPrompt({ sourcePath, sessionId: "session-2", byteLength: 16 }),
    ],
  };

  const result = await distillSignals(options);

  expect(result.rules.length).toBe(1);
  expect(result.rules[0]?.sessions).toBe(2);
  expect(result.rules[0]?.source).toBe("mined");
  expect(result.rules[0]?.status).toBe("candidate");
  expect(result.rules[0]?.evidence.for).toHaveLength(2);
  expect(result.rules[0]?.evidence.against).toEqual([]);
});
