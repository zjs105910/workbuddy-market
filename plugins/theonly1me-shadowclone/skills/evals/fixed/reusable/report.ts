import path from "node:path";
import { fingerprint } from "../../shared/structured";
import { readFrozenArtifact, writeFrozenArtifact } from "../workflow/preparation";
import { completedAttempt, recoverReceipt } from "./attempts";
import { readReusableSuite } from "./freeze";
import { fixedSuiteInterval } from "./intervals";
import { setupPerformance } from "./scoring";
import { receiptSchema, type FrozenSuite, type Receipt, type Setup } from "./schema";
import { invocationAccounting, readInvocationLedger, type InvocationLedger } from "./accounting";

export function reusableReport(options: {
  suite: FrozenSuite;
  receipt: Receipt;
  ledger?: InvocationLedger;
}) {
  if (options.receipt.suiteFingerprint !== fingerprint(options.suite))
    throw new Error("Receipt fingerprint differs from frozen suite.");
  recoverReceipt(options);
  const setups: Setup[] =
    options.suite.experiment === "learning"
      ? options.suite.phase === "preflight"
        ? ["bare", "told"]
        : ["bare", "skills", "routing", "told", "deep"]
      : ["skills", "routing"];
  const scores = setups.map((setup) => ({
    ...setupPerformance({ ...options, setup }),
    interval: fixedSuiteInterval({ ...options, candidate: setup }),
  }));
  const pairs: { candidate: Setup; baseline: Setup }[] =
    options.suite.experiment === "learning" && options.suite.phase === "preflight"
      ? [{ candidate: "told", baseline: "bare" }]
      : options.suite.experiment === "learning"
        ? [
            { candidate: "deep", baseline: "told" },
            { candidate: "deep", baseline: "routing" },
            { candidate: "routing", baseline: "skills" },
          ]
        : [{ candidate: "routing", baseline: "skills" }];
  const comparisons = pairs.map((pair) => {
    const candidate = scores.find((score) => score.setup === pair.candidate)?.score;
    const baseline = scores.find((score) => score.setup === pair.baseline)?.score;
    return {
      ...pair,
      difference:
        candidate === null || candidate === undefined || baseline === null || baseline === undefined
          ? null
          : candidate - baseline,
      interval: fixedSuiteInterval({ ...options, ...pair }),
    };
  });
  const attempts = options.receipt.cells.flatMap((cell) => cell.attempts);
  const bare = scores.find((score) => score.setup === "bare");
  const told = scores.find((score) => score.setup === "told");
  const accounting = invocationAccounting(options);
  return {
    protocol: "preference-respect-v3",
    status:
      scores.every((score) => score.complete) &&
      options.receipt.status === "complete" &&
      accounting.complete
        ? "complete"
        : "incomplete",
    experiment: options.suite.experiment,
    phase: options.suite.phase,
    host: options.suite.host,
    product: options.suite.product,
    benchmarkFingerprint: options.suite.benchmarkFingerprint,
    graderFingerprint: options.suite.graderFingerprint,
    caseFingerprint: fingerprint(options.suite.cases),
    guidanceFingerprint: fingerprint(options.suite.environments),
    scores,
    comparisons,
    learning: options.suite.learning,
    learningOrigin: options.suite.learningOrigin ?? null,
    calls: accounting.calls,
    accounting,
    headroom:
      options.suite.phase === "preflight"
        ? {
            bareNearCeiling:
              bare?.score !== null && bare?.score !== undefined ? bare.score >= 0.95 : null,
            toldMisses:
              told?.perPreference
                .filter((preference) => preference.score !== null && preference.score < 1)
                .map((preference) => preference.family) ?? [],
            controlFailures: (told?.correctness.fail ?? 0) + (told?.safety.fail ?? 0),
            limitation:
              "One repetition per public case; diagnostics only, not qualification or an improvement estimate.",
          }
        : null,
    attempts: attempts.length,
    confirmedInfrastructureFailures: attempts.filter((attempt) =>
      attempt.diagnostics.some((diagnostic) => diagnostic.confirmedInfrastructure),
    ).length,
    incompleteCells: options.receipt.cells
      .filter((cell) => completedAttempt(cell)?.record?.status !== "complete")
      .map((cell) => ({ caseId: cell.caseId, setup: cell.setup, repetition: cell.repetition })),
    limitations: [
      "Synthetic fixed suite; model headroom requires development preflight.",
      options.suite.phase === "preflight"
        ? "Bare/told diagnostic only, one repetition, no learning calls or confidence interval."
        : "Three shared learning preparations; intervals keep every case weight fixed.",
      "Published/missing/unsupported guidance inspection is heuristic and requires review of the private preparation artifacts.",
      "Development results are not held-out qualification.",
    ],
  };
}

export async function reportReusableSuite(file: string) {
  const suite = await readReusableSuite(file);
  const receipt = receiptSchema.parse(
    await readFrozenArtifact(path.join(path.dirname(file), "receipt.json")),
  );
  const ledger = await readInvocationLedger(path.dirname(file));
  const report = reusableReport({ suite, receipt, ledger });
  await writeFrozenArtifact({ file: path.join(path.dirname(file), "report.json"), value: report });
  return report;
}

export async function compareReusableRuns(options: {
  baselineFile: string;
  candidateFile: string;
}) {
  const baseline = await readReusableSuite(options.baselineFile);
  const candidate = await readReusableSuite(options.candidateFile);
  const matching = (suite: FrozenSuite) => ({
    benchmark: suite.benchmarkFingerprint,
    grader: suite.graderFingerprint,
    runtime: suite.runtime,
    host: suite.host,
    cases: suite.cases,
    learner: suite.learner,
    limits: suite.limits,
    experiment: suite.experiment,
    phase: suite.phase,
    repetitions: suite.repetitions,
  });
  if (fingerprint(matching(baseline)) !== fingerprint(matching(candidate)))
    throw new Error(
      "Branch comparisons require matched cases, preparation inputs and learner, host, model, effort, runtime, and limits.",
    );
  const reports = {
    baseline: await reportReusableSuite(options.baselineFile),
    candidate: await reportReusableSuite(options.candidateFile),
  };
  return {
    ...reports,
    differences: reports.baseline.scores.map((before) => {
      const after = reports.candidate.scores.find((score) => score.setup === before.setup);
      return {
        setup: before.setup,
        difference:
          before.score === null || after?.score === null || after?.score === undefined
            ? null
            : after.score - before.score,
      };
    }),
  };
}
