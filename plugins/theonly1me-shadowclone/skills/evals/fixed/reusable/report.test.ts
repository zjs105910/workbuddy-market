import { expect, test } from "bun:test";
import { fixtureReceipt, fixtureSuite } from "./testFixtures";
import { reusableReport } from "./report";
import { fixedSuiteInterval } from "./intervals";
import { families } from "./schema";

test("every family contributes one eighth even with extra checks", () => {
  const suite = fixtureSuite();
  const receipt = fixtureReceipt(suite);
  for (const cell of receipt.cells) {
    const entry = suite.cases.find((entry) => entry.task.id === cell.caseId);
    if (entry?.family === "length" && cell.setup === "skills") {
      const attempt = cell.attempts[0];
      if (!attempt) throw new Error("Missing fixture attempt.");
      attempt.checks = attempt.checks.map((check) => ({ ...check, verdict: "fail" }));
    }
  }
  const report = reusableReport({ suite, receipt });
  expect(report.scores.find((score) => score.setup === "skills")?.score).toBe(0.875);
  expect(report.comparisons.find((pair) => pair.baseline === "skills")?.difference).toBe(0.125);
  expect(report.scores.find((score) => score.setup === "skills")?.perPreference).toHaveLength(
    families.length,
  );
  expect(fixedSuiteInterval({ suite, receipt, candidate: "deep", baseline: "skills" })?.upper).toBe(
    0.125,
  );
});

test("missing execution and unconfirmed identities leave the fixed denominator incomplete", () => {
  const suite = fixtureSuite();
  const receipt = fixtureReceipt(suite);
  const cell = receipt.cells.find((cell) => cell.setup === "deep");
  if (!cell) throw new Error("Missing deep fixture.");
  cell.attempts = [];
  const report = reusableReport({ suite, receipt });
  expect(report.status).toBe("incomplete");
  expect(report.scores.find((score) => score.setup === "deep")?.score).toBeNull();
  expect(report.scores.find((score) => score.setup === "deep")?.sessions).toBe(72);
});

test("correctness and safety failures remain distinct from known preference adherence", () => {
  const suite = fixtureSuite();
  const receipt = fixtureReceipt(suite);
  const attempt = receipt.cells[0]?.attempts[0];
  if (!attempt?.record) throw new Error("Expected synthetic record.");
  attempt.record.correctness = "fail";
  attempt.record.safety = "fail";
  const report = reusableReport({ suite, receipt });
  expect(report.scores[0]?.score).toBe(1);
  expect(report.scores[0]?.correctness.fail).toBe(1);
  expect(report.scores[0]?.safety.fail).toBe(1);
});

test("a model identity mismatch or cleanup gap invalidates execution evidence", () => {
  const suite = fixtureSuite();
  const receipt = fixtureReceipt(suite);
  const attempt = receipt.cells[0]?.attempts[0];
  const turn = attempt?.record?.turns[0];
  if (!attempt || !turn) throw new Error("Expected synthetic attempt.");
  turn.resolvedModel = "another-model";
  expect(reusableReport({ suite, receipt }).scores[0]?.score).toBeNull();
  turn.resolvedModel = "synthetic";
  attempt.diagnostics.push({
    stage: "cleanup",
    confirmedInfrastructure: true,
    message: "Cleanup failed.",
    details: "Fixture failure.",
  });
  expect(reusableReport({ suite, receipt }).scores[0]?.score).toBeNull();
});

test("an interruption between ledger reservation and receipt persistence remains charged and incomplete", () => {
  const suite = fixtureSuite();
  const receipt = fixtureReceipt(suite);
  const observed = reusableReport({ suite, receipt }).calls;
  const ledger = {
    version: 1 as const,
    limitUsd: null,
    spentUsd: 0,
    calls: observed + 1,
    maximumCalls: suite.limits.maximumCalls,
    pending: true,
    unknownCost: true,
  };
  const report = reusableReport({ suite, receipt, ledger });
  expect(report.calls).toBe(observed + 1);
  expect(report.accounting.unattributedCalls).toBe(1);
  expect(report.status).toBe("incomplete");
  expect(() =>
    reusableReport({ suite, receipt, ledger: { ...ledger, calls: observed - 1 } }),
  ).toThrow("Invocation ledger");
});

test("foreign working changes and duplicate preference evidence cannot complete the headline", () => {
  const suite = fixtureSuite();
  const receipt = fixtureReceipt(suite);
  const cell = receipt.cells.find(
    (cell) => cell.caseId === "git-ready-to-ship" && cell.setup === "bare",
  );
  const attempt = cell?.attempts[0];
  if (!attempt?.record) throw new Error("Expected synthetic git evidence.");
  attempt.record.productTreeFingerprint = "f".repeat(64);
  expect(reusableReport({ suite, receipt }).scores[0]?.score).toBeNull();
  attempt.record.productTreeFingerprint = suite.product.tree;
  const first = attempt.checks[0];
  if (!first || attempt.checks.length < 2) throw new Error("Expected several check ids.");
  attempt.checks[1] = { ...first };
  expect(reusableReport({ suite, receipt }).scores[0]?.score).toBeNull();
});
