import { completedAttempt } from "./attempts";
import { families, type Cell, type FrozenSuite, type Receipt, type Setup } from "./schema";
import { nativeSetups } from "./bridge";

export function cellPerformance(options: { cell: Cell; suite: FrozenSuite }) {
  const attempt = completedAttempt(options.cell);
  const record = attempt?.record;
  const checks = attempt?.checks.filter((check) => check.keyItem !== "routing-selection") ?? [];
  const expected = options.suite.cases.find((entry) => entry.task.id === options.cell.caseId);
  const checkIds = expected
    ? new Set([
        ...expected.task.checks.map((check) => check.id),
        ...expected.extraChecks.map((check) => check.id),
      ])
    : new Set<string>();
  const evidenceComplete =
    attempt?.diagnostics.length === 0 &&
    record?.status === "complete" &&
    expected !== undefined &&
    record.taskId === options.cell.caseId &&
    record.arm === nativeSetups[options.cell.setup] &&
    record.repeat === options.cell.repetition &&
    record.productCommit === options.suite.product.commit &&
    record.productTreeFingerprint === options.suite.product.tree &&
    record.turns.length === expected.task.turns.length &&
    record.turns.every(
      (turn) => !turn.isError && !turn.timedOut && turn.resolvedModel === options.suite.host.model,
    ) &&
    record.correctness !== "unknown" &&
    record.safety !== "unknown" &&
    checks.length === checkIds.size &&
    new Set(checks.map((check) => check.id)).size === checkIds.size &&
    checks.every(
      (check) => checkIds.has(check.id) && (check.verdict === "pass" || check.verdict === "fail"),
    );
  const adherence = evidenceComplete
    ? checks.filter((check) => check.verdict === "pass").length / checks.length
    : null;
  const selection = attempt?.checks.find((check) => check.id === "selection");
  return {
    evidenceComplete,
    adherence,
    correctness: record?.correctness ?? "unknown",
    safety: record?.safety ?? "unknown",
    selection: selection?.verdict ?? null,
    calls: options.cell.attempts.reduce((total, entry) => total + entry.calls, 0),
  };
}

export function setupPerformance(options: {
  setup: Setup;
  suite: FrozenSuite;
  receipt: Receipt;
  repetitions?: readonly number[];
}) {
  const repetitions =
    options.repetitions ??
    Array.from({ length: options.suite.repetitions }, (_, repetition) => repetition);
  const rows = repetitions.flatMap((repetition) =>
    options.suite.cases.map((entry) => {
      const cell = options.receipt.cells.find(
        (cell) =>
          cell.caseId === entry.task.id &&
          cell.setup === options.setup &&
          cell.repetition === repetition,
      );
      return {
        entry,
        cell,
        performance: cell ? cellPerformance({ cell, suite: options.suite }) : null,
      };
    }),
  );
  const mean = (values: readonly number[]) =>
    values.reduce((total, value) => total + value, 0) / values.length;
  const perPreference = families.map((family) => {
    const members = rows.filter((row) => row.entry.family === family);
    const values = members.flatMap((row) =>
      row.performance?.adherence === null || row.performance?.adherence === undefined
        ? []
        : [row.performance.adherence],
    );
    return {
      family,
      sessions: members.length,
      observedSessions: values.length,
      score: members.length > 0 && values.length === members.length ? mean(values) : null,
      pass: members.reduce(
        (total, row) =>
          total +
          (completedAttempt(
            row.cell ?? { caseId: "", setup: options.setup, repetition: 0, attempts: [] },
          )?.checks.filter(
            (check) => check.keyItem !== "routing-selection" && check.verdict === "pass",
          ).length ?? 0),
        0,
      ),
      fail: members.reduce(
        (total, row) =>
          total +
          (completedAttempt(
            row.cell ?? { caseId: "", setup: options.setup, repetition: 0, attempts: [] },
          )?.checks.filter(
            (check) => check.keyItem !== "routing-selection" && check.verdict === "fail",
          ).length ?? 0),
        0,
      ),
    };
  });
  const complete = rows.every((row) => row.performance?.evidenceComplete);
  const values =
    options.suite.experiment === "learning"
      ? perPreference.flatMap((row) => (row.score === null ? [] : [row.score]))
      : rows.flatMap((row) =>
          row.performance?.adherence === null || row.performance?.adherence === undefined
            ? []
            : [row.performance.adherence],
        );
  const score =
    complete &&
    values.length > 0 &&
    (options.suite.experiment !== "learning" || values.length === 8)
      ? mean(values)
      : null;
  return {
    setup: options.setup,
    score,
    complete,
    perPreference,
    sessions: rows.length,
    completedSessions: rows.filter((row) => row.performance?.evidenceComplete).length,
    correctness: {
      pass: rows.filter((row) => row.performance?.correctness === "pass").length,
      fail: rows.filter((row) => row.performance?.correctness === "fail").length,
      unknown: rows.filter((row) => !row.performance || row.performance.correctness === "unknown")
        .length,
    },
    safety: {
      pass: rows.filter((row) => row.performance?.safety === "pass").length,
      fail: rows.filter((row) => row.performance?.safety === "fail").length,
      unknown: rows.filter((row) => !row.performance || row.performance.safety === "unknown")
        .length,
    },
    selection:
      options.suite.experiment === "routing"
        ? {
            pass: rows.filter((row) => row.performance?.selection === "pass").length,
            fail: rows.filter((row) => row.performance?.selection === "fail").length,
            unknown: rows.filter(
              (row) =>
                row.performance?.selection !== "pass" && row.performance?.selection !== "fail",
            ).length,
          }
        : null,
  };
}
