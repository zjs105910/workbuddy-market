import { expect, test } from "bun:test";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { engineRun } from "../../native/study/fixtures";
import { prepareWorkflowEnvironments } from "./preparation";
import { learnWorkflowEnvironments } from "./learning";
import { syntheticLearner } from "./syntheticLearner";
import { prepareWorkflowSuite } from "./freeze";
import { runWorkflowSuite } from "./index";
import { workflowDefinition } from "./definition";
import type { NativeEngineRunner } from "@shadowclone/agents";

test.skipIf(process.platform !== "darwin")("four-setup execution preserves all cells, resumes two-turn tasks, and never reruns completed sessions", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "four-setup-execution-"));
  try {
    const preparationFile = await prepareWorkflowEnvironments({ directory: path.join(directory, "environments"), engine: "codex", model: "synthetic-learner", effort: "medium", maximumCalls: 16, cliVersion: "synthetic-cli" });
    const prepared = await learnWorkflowEnvironments({ preparationFile, managedConfigPath: null, runner: syntheticLearner({ prompts: [] }) });
    const suiteFile = await prepareWorkflowSuite({ directory: path.join(directory, "scored"), environmentsFile: prepared.environmentsFile,
      engine: "codex", model: "synthetic-scored", effort: "medium", repetitions: 1, cliVersion: "synthetic-cli" });
    let calls = 0;
    let resumed = 0;
    const runner: NativeEngineRunner = async options => {
      calls += 1;
      if (options.resumeSessionId) resumed += 1;
      const task = workflowDefinition.tasks.find(candidate => candidate.turns.includes(options.prompt));
      if (!task) throw new Error("Unexpected scored prompt");
      for (const file of task.acceptance?.reference ?? []) await Bun.write(path.join(options.directory, file.path), file.content);
      return engineRun({ resolvedModel: "synthetic-scored", cliVersion: "synthetic-cli", text: "Default sort converts values to strings. Use (left, right) => left - right for ascending numeric order." });
    };
    const report = await runWorkflowSuite({ suiteFile, runner });
    expect(report.status).toBe("complete");
    expect(report.cells).toHaveLength(28);
    expect(report.arms.map(arm => arm.preferenceScore)).toEqual([100, 100, 100, 100]);
    expect(calls).toBe(32);
    expect(resumed).toBe(4);
    await runWorkflowSuite({ suiteFile, runner });
    expect(calls).toBe(32);
  } finally { await rm(directory, { recursive: true, force: true }); }
}, 180_000);
