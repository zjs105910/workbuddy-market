import { expect, test } from "bun:test";
import { fixedReport, compareFixedReports } from "./report";
import { fixedFixture } from "./testFixtures";

test("fixed cases yield a score per setup after all cells complete", async () => {
  const fixture = await fixedFixture();
  try {
    const report = fixedReport(fixture);
    expect(report.status).toBe("complete");
    expect(report.cells).toHaveLength(21);
    expect(report.arms.map((arm) => [arm.arm, arm.score, arm.adherenceScore])).toEqual([
      ["bare", 100, 100], ["profile", 100, 100], ["shadowclone", 100, 100],
    ]);
    expect(report.cells.find((cell) => cell.taskId === "explicit-comment-override")?.verdict).toBe("pass");
  } finally { await fixture.cleanup(); }
});

test("missing, interrupted, timed out, and unknown evidence cannot produce a final score", async () => {
  const fixture = await fixedFixture();
  try {
    const [first] = fixture.receipt.runs;
    if (!first) throw new Error("Missing fixture run");
    const receipts = [
      { ...fixture.receipt, runs: fixture.receipt.runs.slice(1) },
      { ...fixture.receipt, runs: [{ ...first, status: "error" as const }, ...fixture.receipt.runs.slice(1)] },
      { ...fixture.receipt, runs: [{ ...first, turns: first.turns.map((turn) => ({ ...turn, timedOut: true })) }, ...fixture.receipt.runs.slice(1)] },
      { ...fixture.receipt, runs: [{ ...first, correctness: "unknown" as const }, ...fixture.receipt.runs.slice(1)] },
    ];
    for (const receipt of receipts) {
      const report = fixedReport({ frozen: fixture.frozen, receipt });
      expect(report.status).toBe("incomplete");
      expect(report.arms.every((arm) => arm.score === null)).toBe(true);
      expect(report.cells).toHaveLength(21);
    }
  } finally { await fixture.cleanup(); }
});

test("grading uses generated evidence and retains functional failures even when stored grades claim a pass", async () => {
  const fixture = await fixedFixture();
  try {
    const runs = fixture.receipt.runs.map((run) => run.arm === "bare" ? { ...run, correctness: "fail" as const,
      turns: run.taskId === "concise-advice" ? run.turns.map((turn) => ({ ...turn, response: "An unrelated answer." })) : run.turns,
      files: run.files.map((file) => ({ ...file, after: `${file.after ?? ""}\n// Added explanation.\n` })),
      checks: [{ id: "comments", keyItem: "comments", verdict: "pass" as const, evidence: "Untrusted cached result." }] } : run);
    const report = fixedReport({ frozen: fixture.frozen, receipt: { ...fixture.receipt, runs } });
    expect(report.status).toBe("complete");
    expect(report.arms.find((arm) => arm.arm === "bare")?.score).toBe(0);
    expect(report.cells.find((cell) => cell.arm === "bare" && cell.taskId === "new-api")?.checks.find((check) => check.id === "comments")?.verdict).toBe("fail");
    expect(report.cells).toHaveLength(21);
  } finally { await fixture.cleanup(); }
});

test("duplicate cells, foreign revisions, and mismatched model identities are rejected or incomplete", async () => {
  const fixture = await fixedFixture();
  try {
    const [first] = fixture.receipt.runs;
    if (!first) throw new Error("Missing fixture run");
    expect(() => fixedReport({ frozen: fixture.frozen, receipt: { ...fixture.receipt, runs: [...fixture.receipt.runs, first] } })).toThrow("duplicate");
    expect(() => fixedReport({ frozen: fixture.frozen, receipt: { ...fixture.receipt, runs: [{ ...first, productCommit: "b".repeat(40) }] } })).toThrow("revision");
    const runs = fixture.receipt.runs.map((run) => ({ ...run, turns: run.turns.map((turn) => ({ ...turn, resolvedModel: "other-model" })) }));
    expect(fixedReport({ frozen: fixture.frozen, receipt: { ...fixture.receipt, runs } }).status).toBe("incomplete");
  } finally { await fixture.cleanup(); }
});

test("branch comparisons retain the same tasks, grader, host, model, and effort", async () => {
  const fixture = await fixedFixture();
  try {
    const baseline = fixedReport(fixture);
    const candidate = { ...baseline, product: { ...baseline.product, commit: "b".repeat(40), branch: "candidate" } };
    expect(compareFixedReports({ baseline, candidate }).comparisons.map((comparison) => comparison.point)).toEqual([0, 0, 0]);
    expect(() => compareFixedReports({ baseline, candidate: { ...candidate, graderFingerprint: "changed" } })).toThrow("identical");
    expect(() => compareFixedReports({ baseline, candidate: { ...candidate, configuration: { ...candidate.configuration, model: "other" } } })).toThrow("identical");
    expect(() => compareFixedReports({ baseline, candidate: { ...candidate, status: "incomplete" } })).toThrow("complete");
    expect(() => compareFixedReports({ baseline, candidate: { ...candidate, cells: candidate.cells.slice(1) } })).toThrow("matrix");
  } finally { await fixture.cleanup(); }
});
