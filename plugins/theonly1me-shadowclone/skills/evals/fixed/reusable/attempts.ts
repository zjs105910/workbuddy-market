import type { Attempt, Cell, FrozenSuite, Receipt } from "./schema";
import { fingerprint } from "../../shared/structured";

export function matrixCells(suite: FrozenSuite): Cell[] {
  const setups =
    suite.experiment === "learning"
      ? suite.phase === "preflight"
        ? (["bare", "told"] as const)
        : (["bare", "skills", "routing", "told", "deep"] as const)
      : (["skills", "routing"] as const);
  return Array.from({ length: suite.repetitions }, (_, repetition) => repetition).flatMap(
    (repetition) =>
      suite.cases.flatMap((entry) =>
        setups.map((setup) => ({ caseId: entry.task.id, setup, repetition, attempts: [] })),
      ),
  );
}

export function retryEligible(cell: Cell) {
  const attempt = cell.attempts.at(-1);
  return (
    cell.attempts.length === 1 &&
    attempt?.status === "complete" &&
    attempt.diagnostics.length > 0 &&
    attempt.diagnostics.every((diagnostic) => diagnostic.confirmedInfrastructure) &&
    attempt.record?.correctness !== "fail" &&
    attempt.record?.safety !== "fail" &&
    !attempt.checks.some((check) => check.verdict === "fail")
  );
}

export function completedAttempt(cell: Cell): Attempt | undefined {
  const attempt = cell.attempts.at(-1);
  return attempt?.status === "complete" ? attempt : undefined;
}

export function recoverReceipt(options: { suite: FrozenSuite; receipt: Receipt }) {
  if (options.receipt.suiteFingerprint !== fingerprint(options.suite))
    throw new Error("Interrupted receipt belongs to a different suite.");
  const expected = matrixCells(options.suite);
  const key = (cell: Cell) => `${cell.caseId}/${cell.setup}/${cell.repetition}`;
  if (
    options.receipt.cells.length !== expected.length ||
    new Set(options.receipt.cells.map(key)).size !== expected.length ||
    expected.some((cell) => !options.receipt.cells.some((actual) => key(cell) === key(actual)))
  )
    throw new Error("Receipt ownership matrix changed.");
  return {
    ...options.receipt,
    status: "running" as const,
    cells: options.receipt.cells.map((cell) => ({
      ...cell,
      attempts: cell.attempts.map((attempt) =>
        attempt.status === "running"
          ? {
              ...attempt,
              status: "interrupted" as const,
              diagnostics: [
                ...attempt.diagnostics,
                {
                  stage: "execution" as const,
                  confirmedInfrastructure: false,
                  message: "Interrupted dispatch retained without automatic retry.",
                  details: "The previous native invocation may have consumed its reservation.",
                },
              ],
            }
          : attempt,
      ),
    })),
  };
}
