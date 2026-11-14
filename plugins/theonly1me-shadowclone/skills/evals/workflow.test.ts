import { expect, test, afterAll } from "bun:test";
import { mkdtemp, rm } from "node:fs/promises";
import path from "node:path";
import os from "node:os";
import {
  freezeWorkflowTasks,
  reportWorkflowOutcomes,
  workflowConditions,
} from "./workflow";
import { summarizeOutcomes } from "./shared/outcome";

const directories: string[] = [];
afterAll(async () => {
  for (const directory of directories)
    await rm(directory, { recursive: true, force: true });
});

test("frozen workflow tasks cannot be overwritten or changed after results are collected", async () => {
  const directory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-workflow-eval-"),
  );
  directories.push(directory);
  const tasksFile = path.join(directory, "tasks.json");
  await Bun.write(
    tasksFile,
    JSON.stringify([
      {
        id: "held-out-task",
        prompt: "Implement a synthetic counter",
        acceptance: ["The counter increments"],
      },
    ]),
  );
  const frozen = await freezeWorkflowTasks({
    tasksFile,
    outputDirectory: directory,
  });
  await expect(
    freezeWorkflowTasks({ tasksFile, outputDirectory: directory }),
  ).rejects.toThrow("already exists");
  const resultsFile = path.join(directory, "results.json");
  const outcome = {
    accepted: true,
    humanReviewMinutes: 5,
    repeatedCorrections: 1,
    regressions: 0,
    interventions: 1,
    costUsd: null,
    reportedBy: "user",
  };
  const result = {
    suiteFingerprint: frozen.fingerprint,
    taskId: "held-out-task",
    repeat: 0,
    host: "codex",
    hostVersion: "synthetic-version",
    model: "synthetic-model",
    budgetUsd: 1,
    productRevision: "synthetic-revision",
    startedAt: new Date().toISOString(),
    outcome,
  };
  await Bun.write(
    resultsFile,
    JSON.stringify(
      workflowConditions.map((condition) => ({ ...result, condition })),
    ),
  );
  const report = await reportWorkflowOutcomes({
    suiteFile: frozen.filePath,
    resultsFile,
  });
  expect(report.matchedGroups).toBe(1);
  expect(report.conditions[0]?.unknownCostRuns).toBe(1);
  expect(report.conditions[0]?.knownCostUsd).toBeNull();
  const suite = JSON.parse(await Bun.file(frozen.filePath).text());
  await Bun.write(frozen.filePath, JSON.stringify({ ...suite, tasks: [] }));
  await expect(
    reportWorkflowOutcomes({ suiteFile: frozen.filePath, resultsFile }),
  ).rejects.toThrow();
});

test("unknown outcomes and missing costs are not fabricated as zero", () => {
  expect(summarizeOutcomes([])).toMatchObject({
    reported: 0,
    knownCostUsd: null,
  });
});
