import type { RunRecord } from "./record";
import type { StudyArm, StudySuite } from "./schema";

type Count = { readonly followed: number; readonly checked: number };
export type ArmCount = Count & { readonly timesBaseline: number | null };

function countChecks(options: { runs: readonly RunRecord[]; arm: StudyArm; taskIds: readonly string[] }): Count {
  const verdicts = options.runs.filter((run) => run.arm === options.arm && options.taskIds.includes(run.taskId))
    .flatMap((run) => run.checks.map((check) => check.verdict))
    .filter((verdict) => verdict === "pass" || verdict === "fail");
  return { followed: verdicts.filter((verdict) => verdict === "pass").length, checked: verdicts.length };
}

function timesBaseline(options: { count: Count; baseline: Count }): number | null {
  if (options.baseline.followed === 0 || options.count.checked === 0) return null;
  return (options.count.followed / options.count.checked) / (options.baseline.followed / options.baseline.checked);
}

function armCounts(options: { runs: readonly RunRecord[]; taskIds: readonly string[] }): Record<StudyArm, ArmCount> {
  const count = (arm: StudyArm): Count => countChecks({ ...options, arm });
  const baseline = count("bare");
  const entry = (arm: StudyArm): ArmCount => ({ ...count(arm), timesBaseline: arm === "bare" ? null : timesBaseline({ count: count(arm), baseline }) });
  return { bare: entry("bare"), original: entry("original"), "first-time": entry("first-time"), deep: entry("deep") };
}

export function taskResults(options: { suite: StudySuite; runs: readonly RunRecord[] }) {
  return {
    overall: armCounts({ runs: options.runs, taskIds: options.suite.tasks.map((task) => task.id) }),
    tasks: options.suite.tasks.map((task) => ({ taskId: task.id, checks: task.checks.map((check) => check.id), arms: armCounts({ runs: options.runs, taskIds: [task.id] }) })),
  };
}
