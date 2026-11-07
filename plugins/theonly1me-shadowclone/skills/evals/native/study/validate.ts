import type { NativeEngineRunner } from "@shadowclone/agents";
import type { EvaluationBudget } from "../../shared/accounting";
import { writeFrozenFile } from "../files";
import { verifyNativeCandidate } from "../verification";
import { calibrationPassed, judgeConversation } from "./judge";
import type { MatrixEntry, MatrixReceipt } from "./matrix";
import type { DroppedCheck, StudySuite } from "./schema";
import { createStudyWorkspace } from "./workspace";

export function controlEntries(suite: StudySuite): MatrixEntry[] {
  return suite.tasks.flatMap((task) => [0, 1].flatMap((repeat) =>
    (["bare", "told"] as const).map((arm) => ({ arm, taskId: task.id, repeat }))));
}

export async function validateFixtures(options: { suite: StudySuite; outputDirectory: string }) {
  const results: { taskId: string; baseline: string; reference: string; evidence: string }[] = [];

  for (const task of options.suite.tasks) {
    if (!task.acceptance) continue;
    const workspace = await createStudyWorkspace({ ...options, task, arm: "bare" });
    try {
      const verify = () => verifyNativeCandidate({ directory: workspace.directory, homeDirectory: workspace.homeDirectory, scenario: { acceptance: task.acceptance } });
      const baseline = await verify();
      for (const file of task.acceptance.reference) await writeFrozenFile({ directory: workspace.directory, file });
      const reference = await verify();
      results.push({ taskId: task.id, baseline: baseline.correctness, reference: reference.correctness,
        evidence: reference.correctness === "pass" ? "" : reference.evidence.slice(-600) });
    } finally {
      await workspace.cleanup();
    }
  }

  return { results, passed: results.every((result) => result.baseline === "fail" && result.reference === "pass") };
}

export async function calibrateJudges(options: {
  suite: StudySuite; runner: NativeEngineRunner; budget: EvaluationBudget; outputDirectory: string;
}): Promise<{ taskId: string; checkId: string; passed: boolean; verdicts: string[] }[]> {
  const results = [];

  for (const task of options.suite.tasks) {
    for (const check of task.checks) {
      if (check.kind !== "judged") continue;
      const verdicts: string[] = [];
      let passed = true;
      for (const example of check.calibration) {
        const { verdict } = await judgeConversation({ ...options, check, conversation: example.conversation, files: [] });
        verdicts.push(`${example.label}:${verdict}`);
        passed &&= calibrationPassed({ label: example.label, verdict });
      }
      results.push({ taskId: task.id, checkId: check.id, passed, verdicts });
    }
  }

  return results;
}

export function controlDecisions(options: {
  suite: StudySuite; receipt: MatrixReceipt; calibration: readonly { taskId: string; checkId: string; passed: boolean }[];
}): DroppedCheck[] {
  const dropped: DroppedCheck[] = [];

  for (const task of options.suite.tasks) {
    for (const check of task.checks) {
      const verdicts = (arm: "bare" | "told") => options.receipt.runs.filter((run) => run.arm === arm && run.taskId === task.id)
        .map((run) => run.checks.find((entry) => entry.id === check.id)?.verdict ?? "unknown");
      const told = verdicts("told");
      const bare = verdicts("bare");
      const calibrated = check.kind !== "judged" || options.calibration.some((entry) => entry.taskId === task.id && entry.checkId === check.id && entry.passed);
      const drop = (reason: DroppedCheck["reason"]) => dropped.push({ taskId: task.id, checkId: check.id, reason });
      if (!calibrated) drop("calibration-failed");
      else if (told.includes("not-applicable") || (bare.length > 0 && bare.every((verdict) => verdict === "not-applicable"))) drop("not-applicable");
      else if (told.length < 2 || told.some((verdict) => verdict !== "pass")) drop("told-failed");
      else if (!bare.includes("fail")) drop("default-behavior");
    }
  }

  return dropped;
}

export function freezeValidatedSuite(options: { suite: StudySuite; dropped: readonly DroppedCheck[] }): StudySuite {
  const isDropped = (taskId: string, checkId: string) => options.dropped.some((entry) => entry.taskId === taskId && entry.checkId === checkId);
  const tasks = options.suite.tasks
    .map((task) => ({ ...task, checks: task.checks.filter((check) => !isDropped(task.id, check.id)) }))
    .filter((task) => task.checks.length > 0);
  return { ...options.suite, tasks, droppedChecks: [...options.dropped] };
}

export function achievableSuite(options: { candidates: StudySuite; dropped: readonly DroppedCheck[] }): StudySuite {
  return freezeValidatedSuite({ suite: options.candidates, dropped: options.dropped.filter((entry) => entry.reason !== "default-behavior") });
}
