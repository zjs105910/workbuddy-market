import { bootstrapDifference, bootstrapRate, taskWeightedRate } from "../../native/study/report";
import { workflowArms, workflowDefinition } from "./definition";
import type { WorkflowCell } from "./cells";

export function preferenceObservations(options: { cells: WorkflowCell[]; arm: typeof workflowArms[number] }) {
  return options.cells.filter(cell => cell.arm === options.arm).flatMap(cell => cell.preferences.map(check => ({
    taskId: cell.taskId, sessionId: `${cell.taskId}/${cell.repeat}`, keyItem: check.keyItem, passed: check.verdict === "pass", skillRead: null,
  })));
}

export function workflowScores(options: { cells: WorkflowCell[]; complete: boolean; seed: number; samples: number }) {
  const tasks = workflowDefinition.tasks.map(task => task.id);
  return workflowArms.map(arm => {
    const selected = options.cells.filter(cell => cell.arm === arm);
    const checks = selected.flatMap(cell => cell.preferences);
    const observations = preferenceObservations({ cells: options.cells, arm });
    return { arm, expectedSessions: selected.length, expectedPreferences: checks.length,
      preferencesPassed: checks.filter(check => check.verdict === "pass").length,
      preferencesFailed: checks.filter(check => check.verdict === "fail").length,
      preferencesUnknown: checks.filter(check => check.verdict === "unknown").length,
      preferenceScore: options.complete ? 100 * (taskWeightedRate({ observations, tasks }) ?? 0) : null,
      interval: options.complete ? bootstrapRate({ observations, tasks, seed: options.seed, samples: options.samples }) : null,
      wholeTasksPassed: selected.filter(cell => cell.verdict === "pass").length,
      correctnessPassed: selected.filter(cell => cell.correctness === "pass").length,
      safetyPassed: selected.filter(cell => cell.safety === "pass").length };
  });
}

export function workflowComparisons(options: { cells: WorkflowCell[]; complete: boolean; seed: number; samples: number }) {
  const pairs: { left: typeof workflowArms[number]; right: typeof workflowArms[number] }[] = [
    { left: "skills", right: "bare" }, { left: "routing", right: "bare" }, { left: "deep", right: "bare" },
    { left: "routing", right: "skills" }, { left: "deep", right: "routing" }, { left: "deep", right: "skills" },
  ];
  return pairs.map(pair => ({ ...pair, difference: options.complete ? bootstrapDifference({
    left: preferenceObservations({ cells: options.cells, arm: pair.left }), right: preferenceObservations({ cells: options.cells, arm: pair.right }),
    tasks: workflowDefinition.tasks.map(task => task.id), seed: options.seed, samples: options.samples,
  }) : null }));
}
