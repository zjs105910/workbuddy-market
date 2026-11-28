import { expect, test } from "bun:test";
import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import {
  defaultConfig,
  defaultManagedPolicy,
  writeConfig,
  createProjectPaths,
} from "@shadowclone/core";
import type { EngineRunOptions, EngineRunner } from "@shadowclone/agents";
import type { IndexedEvent, CorrectionSignal, OriginScope } from "@shadowclone/sessions";
import { runDeepLearning } from "./deepLearn";
import { decidePendingLearning, readPendingLearning } from "@shadowclone/learning";

const origin: OriginScope = {
  id: "github.com/acme",
  directoryName: "github.com--acme--936913df4a5c268b",
  promotable: true,
};

async function fixture() {
  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-deep-"),
  );
  const paths = createProjectPaths({ homeDirectory, platform: "darwin" });
  await writeConfig({
    configPath: paths.configFile,
    config: {
      ...defaultConfig,
      sources: { ...defaultConfig.sources, "claude-code": true },
      distillation: { deep: true, automatic: false },
    },
  });
  const sourcePath = path.join(paths.claudeProjectsDirectory, "evidence.txt");
  const text = "The user asked for a smaller change.";

  await Bun.write(sourcePath, text);

  const textRef = {
    type: "file" as const,
    sourcePath,
    byteOffset: 0,
    byteLength: Buffer.byteLength(text),
  };
  const signal: CorrectionSignal = {
    kind: "question-answered",
    category: "agent-question",
    label: "an agent question",
    sessionId: "session-1",
    timestamp: 1_788_537_600_000,
    origin,
    repositoryName: null,
    textRefs: [textRef],
  };
  const event: IndexedEvent = {
    id: 1,
    sourcePath,
    source: "claude-code",
    sessionId: signal.sessionId,
    eventId: "event-1",
    parentEventId: null,
    timestamp: signal.timestamp,
    cwd: "/repo",
    gitBranch: null,
    kind: "question-answered",
    tool: null,
    isError: false,
    textRef,
  };

  return { paths, signal, event };
}

function runner(onCall: (options: EngineRunOptions) => void): EngineRunner {
  return (options) => {
    onCall(options);

    return Promise.resolve({
      engine: "claude-code",
      sessionId: "engine-session",
      transcriptPath: null,
      text: "",
      structured: {
        existingRules: [],
        newRules: [
          {
            title: "Keep the change small",
            body: "Choose the smallest change that satisfies the request.",
            section: "workflow",
            observed: "The user chose the smaller scope.",
            evidenceTokens: ["evidence-1"],
            rejectionToken: "",
          },
        ],
      },
      costUsd: 0.01,
      durationMs: 10,
      turns: 1,
      isError: false,
      permissionDenials: [],
      actions: [],
      errorMessage: null,
    });
  };
}

test("semantic dry run calls the engine and writes no local learning state", async () => {
  const { paths, signal, event } = await fixture();
  let calls = 0;
  let confirmations = 0;
  const result = await runDeepLearning({
    signals: [signal],
    events: [event],
    paths,
    policy: defaultManagedPolicy,
    runner: runner(() => {
      calls += 1;
    }),
    engine: "claude-code",
    dryRun: true,
    apply: false,
    confirm: () => {
      confirmations += 1;

      return true;
    },
    writeLine: () => {},
  });

  expect(calls).toBe(1);
  expect(confirmations).toBe(0);
  expect(result.profileUpdated).toBeFalse();
  expect(await Bun.file(paths.profileDirectory).exists()).toBeFalse();
  expect(await Bun.file(paths.distillDirectory).exists()).toBeFalse();
});

test("deep learning forwards the selected model and effort", async () => {
  const { paths, signal, event } = await fixture();
  const requests: EngineRunOptions[] = [];

  await runDeepLearning({
    signals: [signal],
    events: [event],
    paths,
    policy: defaultManagedPolicy,
    runner: runner((options) => {
      requests.push(options);
    }),
    engine: "claude-code",
    model: "claude-sonnet-5",
    reasoningEffort: "medium",
    dryRun: true,
    apply: false,
    writeLine: () => {},
  });

  expect(requests[0]?.model).toBe("claude-sonnet-5");
  expect(requests[0]?.reasoningEffort).toBe("medium");
});

test("default review can decline while apply skips confirmation", async () => {
  const { paths, signal, event } = await fixture();
  let confirmations = 0;
  const common = {
    signals: [signal],
    events: [event],
    paths,
    policy: defaultManagedPolicy,
    runner: runner(() => {}),
    engine: "claude-code" as const,
    dryRun: false,
    writeLine: () => {},
  };
  const declined = await runDeepLearning({
    ...common,
    apply: false,
    confirm: () => {
      confirmations += 1;

      return false;
    },
  });

  expect(confirmations).toBe(1);
  expect(declined.profileUpdated).toBeFalse();
  expect(declined.pendingReview).toBe(1);
  const pending = await readPendingLearning(paths);
  expect(pending.rules).toHaveLength(1);
  expect(pending.rules[0]?.body).toBe("Choose the smallest change that satisfies the request.");
  expect(
    await Bun.file(path.join(paths.profileDirectory, "org")).exists(),
  ).toBeFalse();

  const applied = await runDeepLearning({
    ...common,
    apply: true,
    confirm: () => {
      throw new Error("Apply must skip confirmation");
    },
  });

  expect(applied.profileUpdated).toBeTrue();
  expect((await readPendingLearning(paths)).rules).toHaveLength(0);
  expect(
    await Bun.file(
      path.join(
        paths.profileDirectory,
        "org",
        origin.directoryName,
        "workflow.md",
      ),
    ).exists(),
  ).toBeTrue();
});

test("a reviewed pending rule can be applied or rejected without learning again", async () => {
  const { paths, signal, event } = await fixture();
  const common = {
    signals: [signal],
    events: [event],
    paths,
    policy: defaultManagedPolicy,
    runner: runner(() => {}),
    engine: "claude-code" as const,
    dryRun: false,
    apply: false,
    confirm: () => false,
    writeLine: () => {},
  };

  await runDeepLearning(common);
  const key = (await readPendingLearning(paths)).rules[0]?.key ?? "";
  await decidePendingLearning({ paths, key, action: "apply" });

  expect((await readPendingLearning(paths)).rules).toHaveLength(0);
  expect((await Bun.file(path.join(paths.profileDirectory, "org", origin.directoryName, "workflow.md")).text()))
    .toContain("Choose the smallest change that satisfies the request.");

  await runDeepLearning(common);
  await decidePendingLearning({ paths, key, action: "reject" });
  const rejected = await readPendingLearning(paths);
  expect(rejected.rules).toHaveLength(0);
  expect(rejected.rejectedKeys).toContain(key);

  const later = await runDeepLearning(common);
  expect(later.pendingReview).toBe(0);
  expect((await readPendingLearning(paths)).rules).toHaveLength(0);
});

test("a rejection during learning confirmation prevents the rule from being recorded", async () => {
  const { paths, signal, event } = await fixture();
  const options = { paths, signals: [signal], events: [event], policy: defaultManagedPolicy,
    runner: runner(() => {}), engine: "claude-code" as const, dryRun: false, apply: false, writeLine: () => {} };
  await runDeepLearning({ ...options, confirm: () => false });
  const key = (await readPendingLearning(paths)).rules[0]?.key;
  if (!key) throw new Error("Expected a pending rule");
  const result = await runDeepLearning({ ...options, confirm: async () => {
    await decidePendingLearning({ paths, key, action: "reject" });
    return true;
  } });
  expect(result.profileUpdated).toBeFalse();
  expect((await readPendingLearning(paths)).rejectedKeys).toContain(key);
  expect(await Bun.file(path.join(paths.profileDirectory, "org", origin.directoryName, "workflow.md")).exists()).toBeFalse();
});
