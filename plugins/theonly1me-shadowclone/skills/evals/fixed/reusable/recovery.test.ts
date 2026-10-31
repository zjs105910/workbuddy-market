import { expect, test } from "bun:test";
import { fixtureReceipt, fixtureSuite } from "./testFixtures";
import { matrixCells, recoverReceipt, retryEligible } from "./attempts";
import { invocationCeiling } from "./freeze";
import { fingerprint } from "../../shared/structured";
import { developmentCases } from "./definition";
import { unresolvedInfrastructure } from "./dispatchHold";

test("the full ceiling includes three preparations and every permitted retry", () => {
  const suite = fixtureSuite();
  expect(
    invocationCeiling({ cases: suite.cases, experiment: "learning", preparationCalls: 48 }),
  ).toEqual({
    preparationCalls: 48,
    candidateCalls: 360,
    retryCalls: 360,
    maximumCalls: 720,
    completeExperimentCeiling: 768,
  });
});

test("bounded preflight needs no learning and retains every public case", () => {
  const suite = fixtureSuite({ cases: developmentCases });
  suite.phase = "preflight";
  suite.repetitions = 1;
  expect(
    invocationCeiling({
      cases: developmentCases,
      experiment: "learning",
      phase: "preflight",
      preparationCalls: 0,
    }),
  ).toEqual({
    preparationCalls: 0,
    candidateCalls: 32,
    retryCalls: 32,
    maximumCalls: 64,
    completeExperimentCeiling: 64,
  });
  expect(matrixCells(suite)).toHaveLength(32);
  expect(new Set(matrixCells(suite).map((cell) => cell.setup))).toEqual(new Set(["bare", "told"]));
});

test("only one confirmed infrastructure failure permits a replacement", () => {
  const suite = fixtureSuite();
  const cell = fixtureReceipt(suite).cells[0];
  const attempt = cell?.attempts[0];
  if (!cell || !attempt) throw new Error("Missing fixture attempt.");
  expect(retryEligible(cell)).toBe(false);
  attempt.diagnostics = [
    {
      stage: "mount-create",
      confirmedInfrastructure: true,
      message: "hdiutil failed.",
      details: "exit 1",
    },
  ];
  expect(retryEligible(cell)).toBe(true);
  attempt.diagnostics[0] = {
    stage: "execution",
    confirmedInfrastructure: false,
    message: "Timeout.",
    details: "Unclassified timeout.",
  };
  expect(retryEligible(cell)).toBe(false);
  attempt.diagnostics[0] = {
    stage: "mount-create",
    confirmedInfrastructure: true,
    message: "hdiutil failed.",
    details: "exit 1",
  };
  cell.attempts.push({ ...structuredClone(attempt), number: 2 });
  expect(retryEligible(cell)).toBe(false);
  expect(cell.attempts.reduce((total, entry) => total + entry.calls, 0)).toBe(2);
});

test("ordinary failures are never erased by infrastructure replacement", () => {
  const cell = fixtureReceipt(fixtureSuite()).cells[0];
  const attempt = cell?.attempts[0];
  if (!cell || !attempt?.checks[0]) throw new Error("Missing fixture attempt.");
  attempt.diagnostics = [
    {
      stage: "cleanup",
      confirmedInfrastructure: true,
      message: "Cleanup failed.",
      details: "exit 1",
    },
  ];
  attempt.checks[0].verdict = "fail";
  expect(retryEligible(cell)).toBe(false);
});

test("unresolved fixture infrastructure holds dispatch without replacing model failures", () => {
  const cell = fixtureReceipt(fixtureSuite()).cells[0];
  const attempt = cell?.attempts[0];
  if (!cell || !attempt) throw new Error("Missing fixture attempt.");
  attempt.diagnostics = [
    {
      stage: "setup",
      confirmedInfrastructure: false,
      message: "Setup failed.",
      details: "Fixture invalid.",
    },
  ];
  expect(unresolvedInfrastructure(cell)?.stage).toBe("setup");
  attempt.diagnostics = [
    {
      stage: "mount-create",
      confirmedInfrastructure: true,
      message: "Mount failed.",
      details: "exit 1",
    },
  ];
  expect(unresolvedInfrastructure(cell)).toBeNull();
  cell.attempts.push({ ...structuredClone(attempt), number: 2 });
  expect(unresolvedInfrastructure(cell)?.stage).toBe("mount-create");
  const latest = cell.attempts.at(-1);
  if (!latest) throw new Error("Missing replacement.");
  latest.diagnostics = [
    {
      stage: "execution",
      confirmedInfrastructure: false,
      message: "Model failed.",
      details: "Unclassified timeout.",
    },
  ];
  expect(unresolvedInfrastructure(cell)).toBeNull();
  latest.diagnostics = [
    {
      stage: "cleanup",
      confirmedInfrastructure: false,
      message: "Cleanup failed.",
      details: "Unclassified cleanup failure.",
    },
  ];
  expect(unresolvedInfrastructure(cell)?.stage).toBe("cleanup");
});

test("recovery retains interrupted ownership and rejects stale or duplicate matrices", () => {
  const suite = fixtureSuite();
  const receipt = fixtureReceipt(suite);
  const cell = receipt.cells[0];
  const attempt = cell?.attempts[0];
  if (!cell || !attempt) throw new Error("Missing fixture attempt.");
  attempt.status = "running";
  const recovered = recoverReceipt({ suite, receipt });
  expect(recovered.cells[0]?.attempts[0]?.status).toBe("interrupted");
  expect(retryEligible(recovered.cells[0] ?? cell)).toBe(false);
  expect(() =>
    recoverReceipt({ suite, receipt: { ...receipt, suiteFingerprint: fingerprint("other") } }),
  ).toThrow("different suite");
  expect(() =>
    recoverReceipt({ suite, receipt: { ...receipt, cells: [...receipt.cells.slice(1), cell] } }),
  ).not.toThrow();
  expect(() =>
    recoverReceipt({
      suite,
      receipt: { ...receipt, cells: [...receipt.cells.slice(1), receipt.cells[1] ?? cell] },
    }),
  ).toThrow("ownership");
  expect(
    new Set(matrixCells(suite).map((cell) => `${cell.caseId}/${cell.setup}/${cell.repetition}`))
      .size,
  ).toBe(360);
});
