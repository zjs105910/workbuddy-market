import { expect, test } from "bun:test";
import { studyFixture, studyTask } from "./fixtures";
import { agreedVerdict, calibrationPassed, maskGuidance } from "./judge";
import type { MatrixReceipt } from "./matrix";
import { pendingRun, type RunArmName } from "./record";
import { bootstrapDifference, bootstrapRate, studyReport, taskWeightedRate } from "./report";
import { controlDecisions, freezeValidatedSuite } from "./validate";
import type { StudyVerdict } from "./checkSchema";

function receipt(runs: readonly { arm: RunArmName; taskId: string; repeat: number; verdicts: readonly StudyVerdict[] }[]): MatrixReceipt {
  return {
    protocol: "preference-study-v1", phase: "validation", suiteFingerprint: "0".repeat(64), deadlineAt: 1, status: "complete", failure: null,
    runs: runs.map((entry) => ({
      ...pendingRun(entry), status: "complete",
      checks: entry.verdicts.map((verdict, index) => ({ id: index === 0 ? "commit-shape" : "no-comments", keyItem: index === 0 ? "commit-subject-shape" : "no-added-comments", verdict, evidence: "" })),
    })),
  };
}

test("controls keep checks told passes and bare fails, and drop defaults", async () => {
  const fixture = await studyFixture();
  try {
    const controls = receipt([
      { arm: "told", taskId: "rename-config", repeat: 0, verdicts: ["pass", "pass"] },
      { arm: "told", taskId: "rename-config", repeat: 1, verdicts: ["pass", "pass"] },
      { arm: "bare", taskId: "rename-config", repeat: 0, verdicts: ["fail", "pass"] },
      { arm: "bare", taskId: "rename-config", repeat: 1, verdicts: ["pass", "pass"] },
    ]);
    const dropped = controlDecisions({ suite: fixture.suite, receipt: controls, calibration: [] });
    expect(dropped).toEqual([{ taskId: "rename-config", checkId: "no-comments", reason: "default-behavior" }]);
    const frozen = freezeValidatedSuite({ suite: fixture.suite, dropped });
    expect(frozen.tasks[0]?.checks.map((check) => check.id)).toEqual(["commit-shape"]);
    expect(frozen.droppedChecks).toEqual(dropped);

    const told = receipt([
      { arm: "told", taskId: "rename-config", repeat: 0, verdicts: ["fail", "not-applicable"] },
      { arm: "told", taskId: "rename-config", repeat: 1, verdicts: ["pass", "pass"] },
    ]);
    expect(controlDecisions({ suite: fixture.suite, receipt: told, calibration: [] }).map((entry) => entry.reason)).toEqual(["told-failed", "not-applicable"]);
  } finally {
    await fixture.cleanup();
  }
});

test("rates weight tasks equally and the bootstrap supports only clear differences", () => {
  const entries = (taskId: string, passes: number, total: number) =>
    Array.from({ length: total }, (_, index) => ({ taskId, sessionId: `${taskId}-${index}`, keyItem: "item", passed: index < passes, skillRead: null }));
  const deep = [...entries("one", 3, 3), ...entries("two", 1, 1), ...entries("three", 2, 2)];
  const bare = [...entries("one", 0, 3), ...entries("two", 0, 1), ...entries("three", 1, 2)];
  expect(taskWeightedRate({ observations: [...entries("one", 1, 4), ...entries("two", 1, 1)], tasks: ["one", "two"] })).toBe(0.625);
  const difference = bootstrapDifference({ left: deep, right: bare, tasks: ["one", "two", "three"], seed: 3, samples: 2000 });
  expect(difference.point).toBeCloseTo(5 / 6, 5);
  expect(difference.supported).toBe(true);
  expect(bootstrapDifference({ left: bare, right: bare, tasks: ["one", "two", "three"], seed: 3, samples: 2000 }).supported).toBe(false);
});

test("intervals include run-to-run noise inside a single task", () => {
  const entries = Array.from({ length: 6 }, (_, index) => ({ taskId: "only", sessionId: `session-${index}`, keyItem: "item", passed: index < 3, skillRead: null }));
  const rate = bootstrapRate({ observations: entries, tasks: ["only"], seed: 5, samples: 2000 });
  expect(rate.point).toBe(0.5);
  expect(rate.lower).toBeLessThan(0.5);
  expect(rate.upper).toBeGreaterThan(0.5);
  expect(rate.halfWidth).toBeGreaterThan(0.2);
  const difference = bootstrapDifference({ left: entries, right: entries, tasks: ["only"], seed: 5, samples: 2000 });
  expect(difference.halfWidth).toBeGreaterThan(0.2);
  expect(difference.supported).toBe(false);
});

test("duplicating correlated checks within sessions does not narrow the interval", () => {
  const sessions = [true, true, false];
  const observations = (checksPerSession: number) => sessions.flatMap((passed, index) =>
    Array.from({ length: checksPerSession }, (_, check) => ({
      taskId: "only",
      sessionId: `session-${index}`,
      keyItem: `item-${check}`,
      passed,
      skillRead: null,
    })),
  );
  const single = bootstrapRate({ observations: observations(1), tasks: ["only"], seed: 7, samples: 2000 });
  const repeated = bootstrapRate({ observations: observations(10), tasks: ["only"], seed: 7, samples: 2000 });

  expect(repeated).toEqual(single);
});

test("unknown outcomes do not lower headline adherence or enter detailed counts", async () => {
  const fixture = await studyFixture({ tasks: [studyTask()] });

  try {
    const scored = { ...receipt([
      { arm: "deep", taskId: "rename-config", repeat: 0, verdicts: ["pass", "pass"] },
      { arm: "deep", taskId: "rename-config", repeat: 1, verdicts: ["unknown", "unknown"] },
    ]), phase: "scored" as const };
    const report = studyReport({ suite: fixture.suite, receipt: scored, coverage: {} });

    expect(report.arms.find((arm) => arm.arm === "deep")?.adherence).toBe(1);
    expect(report.counts.overall.deep).toEqual({ followed: 2, checked: 2, timesBaseline: null });
    expect(report.arms.find((arm) => arm.arm === "deep")?.unknown).toBe(2);
  } finally {
    await fixture.cleanup();
  }
});

test("the report separates adherence from fidelity to covered preferences", async () => {
  const fixture = await studyFixture({ tasks: [studyTask()] });
  try {
    const scored = { ...receipt([
      { arm: "deep", taskId: "rename-config", repeat: 0, verdicts: ["pass", "fail"] },
      { arm: "bare", taskId: "rename-config", repeat: 0, verdicts: ["fail", "fail"] },
    ]), phase: "scored" as const };
    const report = studyReport({ suite: fixture.suite, receipt: scored, coverage: {
      deep: [{ keyItem: "commit-subject-shape", status: "covered", file: "home/.agents/skills/names/SKILL.md", route: "description-routed", quote: "Use full words." }],
    } });
    const deep = report.arms.find((arm) => arm.arm === "deep");
    expect(deep?.adherence).toBe(0.5);
    expect(deep?.fidelity).toBe(1);
    expect(deep?.adherenceWhenSkillUnread).toBe(1);
    expect(report.arms.find((arm) => arm.arm === "bare")?.adherence).toBe(0);
  } finally {
    await fixture.cleanup();
  }
});

test("judging masks guidance and requires agreement and calibration", async () => {
  const fixture = await studyFixture();
  try {
    expect(maskGuidance({ text: "I read /tmp/home/.agents/skills/names/SKILL.md and the names skill.", suite: fixture.suite }))
      .toBe("I read [guidance] and the [guidance] skill.");
    expect(agreedVerdict(["pass", "pass"])).toBe("pass");
    expect(agreedVerdict(["pass", "fail"])).toBe("unknown");
    expect(calibrationPassed({ label: "boundary", verdict: "unknown" })).toBe(true);
    expect(calibrationPassed({ label: "fail", verdict: "pass" })).toBe(false);
  } finally {
    await fixture.cleanup();
  }
});
