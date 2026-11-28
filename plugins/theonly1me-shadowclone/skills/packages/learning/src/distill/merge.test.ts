import { expect, test } from "bun:test";
import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import type { EngineRunner } from "@shadowclone/agents";
import { mergeDistilledRules } from "./merge";
import type { DistilledRule } from "./schema";

const rules: readonly DistilledRule[] = [
  {
    title: "Plans before editing",
    body: "Show the plan before changing files.",
    section: "workflow",
  },
  {
    title: "Plan first",
    body: "Present a plan before touching the code.",
    section: "workflow",
  },
];

function runnerReturning(structured: unknown): EngineRunner {
  return () =>
    Promise.resolve({
      engine: "claude-code",
      sessionId: "merge-session",
      transcriptPath: null,
      text: "",
      structured,
      costUsd: 0.01,
      durationMs: 10,
      turns: 1,
      isError: false,
      permissionDenials: [],
      actions: [],
      errorMessage: null,
    });
}

test("retains constituent source indices from engine output", async () => {
  const merged = await mergeDistilledRules({
    rules,
    runner: runnerReturning({
      rules: [
        {
          title: "Plans before editing",
          body: "Show the plan before changing files.",
          section: "workflow",
          sources: [0, 1],
        },
      ],
    }),
    cwd: "/tmp",
  });

  expect(merged.rules.length).toBe(1);
  expect(merged.rules[0]?.sources).toEqual([0, 1]);
});

test("keeps the unmerged rules when the engine returns an unusable shape", async () => {
  const merged = await mergeDistilledRules({
    rules,
    runner: runnerReturning({ summary: "nothing to merge" }),
    cwd: "/tmp",
  });

  expect(merged).toEqual({ rules, dropped: [] });
});

test("reads merge from checkpoint on repeated invocation without calling runner", async () => {
  const checkpointDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-merge-checkpoint-"),
  );
  let callCount = 0;

  const runner: EngineRunner = () => {
    callCount += 1;

    return Promise.resolve({
      engine: "claude-code",
      sessionId: "merge-session",
      transcriptPath: null,
      text: "",
      structured: {
        rules: [
          {
            title: "Plans before editing",
            body: "Show the plan before changing files.",
            section: "workflow",
            sources: [0, 1],
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

  const first = await mergeDistilledRules({
    rules,
    runner,
    cwd: "/tmp",
    checkpointDirectory,
  });

  expect(callCount).toBe(1);
  expect(first.rules.length).toBe(1);

  const second = await mergeDistilledRules({
    rules,
    runner,
    cwd: "/tmp",
    checkpointDirectory,
  });

  expect(callCount).toBe(1);
  expect(second.rules.length).toBe(1);
});

const completeNames: DistilledRule = {
  title: "Use complete names",
  body: "Write full words in identifiers.",
  section: "engineering",
};
const noForcePush: DistilledRule = {
  title: "Never force push",
  body: "Merge the base branch in instead of rewriting history.",
  section: "workflow",
};
const telemetry: DistilledRule = {
  title: "Session telemetry",
  body: "The session ran 14 tool calls.",
  section: "workflow",
};
const distinctRules: readonly DistilledRule[] = [completeNames, noForcePush, telemetry];

test("a rule the engine leaves out of every source is kept unmerged", async () => {
  const merged = await mergeDistilledRules({
    rules: distinctRules,
    runner: runnerReturning({
      rules: [{ ...completeNames, sources: [0] }],
      dropped: [],
    }),
    cwd: "/tmp",
  });

  expect(merged.rules.map((rule) => rule.title)).toEqual([
    "Use complete names",
    "Never force push",
    "Session telemetry",
  ]);
  expect(merged.rules.map((rule) => rule.sources)).toEqual([[0], [1], [2]]);
  expect(merged.dropped).toEqual([]);
});

test("a dropped rule is reported with its reason, and a merged rule cannot also be dropped", async () => {
  const merged = await mergeDistilledRules({
    rules: distinctRules,
    runner: runnerReturning({
      rules: [
        { ...completeNames, sources: [0] },
        { ...noForcePush, sources: [1] },
      ],
      dropped: [
        { index: 2, reason: "It records activity, not guidance." },
        { index: 0, reason: "Duplicate." },
        { index: 9, reason: "Out of range." },
      ],
    }),
    cwd: "/tmp",
  });

  expect(merged.rules.map((rule) => rule.title)).toEqual(["Use complete names", "Never force push"]);
  expect(merged.dropped).toEqual([
    { rule: telemetry, reason: "It records activity, not guidance." },
  ]);
});
