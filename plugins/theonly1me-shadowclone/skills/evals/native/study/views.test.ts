import { expect, test } from "bun:test";
import { turn, run } from "./checks/fixtures";
import { studyFixture, studyTask } from "./fixtures";
import type { MatrixReceipt } from "./matrix";
import { achievableSuite } from "./validate";
import { achievableReport, rescoreStudyReceipt } from "./views";
import { studyReport } from "./report";

const words = (count: number) => Array.from({ length: count }, () => "word").join(" ");
const limit = (id: string, maximum: number) => ({ id, keyItem: "concise-answers", kind: "max-words" as const, turn: 0, maximum });

test("the achievable view keeps checks bare already meets and drops checks told failed", async () => {
  const brief = limit("brief", 50);
  const terse = limit("terse", 5);
  const impossible = limit("impossible", 1);
  const task = studyTask({ mode: "advice", turns: ["how long is the retry cap?"], git: null, checks: [brief, terse, impossible] });
  const fixture = await studyFixture({ tasks: [task] });
  try {
    const dropped = [
      { taskId: task.id, checkId: "brief", reason: "default-behavior" as const },
      { taskId: task.id, checkId: "impossible", reason: "told-failed" as const },
    ];
    const frozen = { ...fixture.suite, tasks: [{ ...task, checks: [terse] }], droppedChecks: dropped };
    expect(achievableSuite({ candidates: fixture.suite, dropped }).tasks[0]?.checks.map((check) => check.id)).toEqual(["brief", "terse"]);

    const session = (arm: "bare" | "deep", count: number) => ({
      ...run({ turns: [turn({ index: 0, response: words(count) })] }), arm, taskId: task.id,
      checks: [{ id: "terse", keyItem: "concise-answers", verdict: count <= 5 ? "pass" as const : "fail" as const, evidence: "" }],
    });
    const receipt: MatrixReceipt = {
      protocol: "preference-study-v1", phase: "scored", suiteFingerprint: "0".repeat(64), deadlineAt: 1, status: "complete", failure: null,
      runs: [session("bare", 10), session("deep", 3)],
    };
    const report = achievableReport({ candidates: fixture.suite, frozen, receipt, coverage: {} });
    expect(report.counts.overall.bare).toEqual({ followed: 1, checked: 2, timesBaseline: null });
    expect(report.counts.overall.deep).toEqual({ followed: 2, checked: 2, timesBaseline: 2 });
    const withDiscarded = { ...receipt, runs: [...receipt.runs, {
      ...session("bare", 100), taskId: "discarded-task", status: "error" as const,
    }] };
    const view = studyReport({ suite: fixture.suite, receipt: withDiscarded, coverage: {} });
    expect(view.recordedRuns).toBe(2);
    expect(view.arms.find((entry) => entry.arm === "bare")?.errors).toBe(0);
    const rescored = rescoreStudyReceipt({ suite: frozen, receipt: withDiscarded });
    expect(rescored.runs).toHaveLength(2);
    expect(rescored.runs.find((entry) => entry.arm === "bare")?.checks[0]?.verdict).toBe("fail");
  } finally {
    await fixture.cleanup();
  }
});
