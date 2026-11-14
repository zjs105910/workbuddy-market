import { expect, test } from "bun:test";
import { workflowReport, compareWorkflowReports } from "./report";
import { workflowFixture } from "./testFixtures";

test("four setups retain all preference checks and give partial credit with equal task weights", async () => {
  const fixture = await workflowFixture();
  try {
    const receipt = { ...fixture.receipt, runs: fixture.receipt.runs.map(run => run.arm === "original" && run.taskId === "new-api"
      ? { ...run, turns: run.turns.map(turn => ({ ...turn, response: "word ".repeat(81) })) } : run) };
    const report = workflowReport({ frozen: fixture.frozen, receipt });
    expect(report.status).toBe("complete");
    expect(report.cells).toHaveLength(28);
    expect(report.arms.map(arm => arm.arm)).toEqual(["bare", "skills", "routing", "deep"]);
    expect(report.arms.every(arm => arm.expectedPreferences === 25)).toBeTrue();
    const skills = report.arms.find(arm => arm.arm === "skills");
    expect(skills?.preferenceScore).toBeCloseTo(100 * (1 - 1 / 5 / 7), 8);
    expect(skills?.preferencesPassed).toBe(24);
    expect(skills?.wholeTasksPassed).toBe(6);
    expect(skills?.correctnessPassed).toBe(7);
    expect(report.comparisons).toHaveLength(6);
  } finally { await fixture.cleanup(); }
});

test("missing fourth-arm cells and unconfirmed model runs retain their denominator and prevent a final score", async () => {
  const fixture = await workflowFixture();
  try {
    const [first] = fixture.receipt.runs;
    if (!first) throw new Error("Missing fixture run");
    const receipts = [
      { ...fixture.receipt, runs: fixture.receipt.runs.filter(run => run.arm !== "deep") },
      { ...fixture.receipt, runs: fixture.receipt.runs.map(run => ({ ...run, turns: run.turns.map(turn => ({ ...turn, resolvedModel: null })) })) },
      { ...fixture.receipt, runs: [{ ...first, correctness: "unknown" as const }, ...fixture.receipt.runs.slice(1)] },
      { ...fixture.receipt, runs: [{ ...first, files: [] }, ...fixture.receipt.runs.slice(1)] },
    ];
    for (const receipt of receipts) {
      const report = workflowReport({ frozen: fixture.frozen, receipt });
      expect(report.status).toBe("incomplete");
      expect(report.cells).toHaveLength(28);
      expect(report.arms.every(arm => arm.preferenceScore === null && arm.expectedPreferences === 25)).toBeTrue();
    }
  } finally { await fixture.cleanup(); }
});

test("correctness and safety failures do not change the preference share", async () => {
  const fixture = await workflowFixture();
  try {
    const runs = fixture.receipt.runs.map(run => run.arm === "bare" ? { ...run, correctness: "fail" as const, safety: "fail" as const } : run);
    const report = workflowReport({ frozen: fixture.frozen, receipt: { ...fixture.receipt, runs } });
    expect(report.arms.find(arm => arm.arm === "bare")?.preferenceScore).toBe(100);
    expect(report.arms.find(arm => arm.arm === "bare")?.correctnessPassed).toBe(1);
    expect(report.arms.find(arm => arm.arm === "bare")?.safetyPassed).toBe(0);
    expect(report.arms.find(arm => arm.arm === "bare")?.wholeTasksPassed).toBe(0);
  } finally { await fixture.cleanup(); }
});

test("reports reject duplicates, foreign revisions, and mismatched branch inputs", async () => {
  const fixture = await workflowFixture();
  try {
    const [first] = fixture.receipt.runs;
    if (!first) throw new Error("Missing fixture run");
    expect(() => workflowReport({ frozen: fixture.frozen, receipt: { ...fixture.receipt, runs: [...fixture.receipt.runs, first] } })).toThrow("duplicate");
    expect(() => workflowReport({ frozen: fixture.frozen, receipt: { ...fixture.receipt, runs: [{ ...first, productTreeFingerprint: "changed" }] } })).toThrow("revision");
    const baseline = workflowReport(fixture);
    expect(compareWorkflowReports({ baseline, candidate: baseline }).comparisons.map(comparison => comparison.point)).toEqual([0, 0, 0, 0]);
    expect(() => compareWorkflowReports({ baseline, candidate: { ...baseline, cells: baseline.cells.filter(cell => cell.arm !== "deep") } })).toThrow("matrix");
    expect(() => compareWorkflowReports({ baseline, candidate: { ...baseline, configuration: { ...baseline.configuration, corpusFingerprint: "changed" } } })).toThrow("matching");
  } finally { await fixture.cleanup(); }
});
