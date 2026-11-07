import { mkdir } from "node:fs/promises";
import path from "node:path";
import { runNativeEngine, type NativeEngineRunner } from "@shadowclone/agents";
import { nativeFailure } from "../../native/diagnostics";
import { runStudySession } from "../../native/study/session";
import { pendingRun } from "../../native/study/record";
import { fingerprint } from "../../shared/structured";
import { evaluationBudget, budgetSchema } from "../../shared/accounting";
import { lockEvaluation } from "../../shared/lock";
import { readFrozenArtifact, writeFrozenArtifact } from "../workflow/preparation";
import { authorizeFixedRun } from "../index";
import { readReusableSuite } from "./freeze";
import { matrixCells, recoverReceipt, retryEligible } from "./attempts";
import { gradeCase, gradeCorrectness, routingSelection } from "./grading";
import { nativeSuite, nativeSetups, selectedEnvironment } from "./bridge";
import { requireProduct } from "./preparation";
import { receiptSchema, scopeSchema, type Attempt, type Receipt } from "./schema";
import { validateReusableSuite } from "./sandbox";
import { confirmedProviderPause } from "./providerPause";
import { unresolvedInfrastructure } from "./dispatchHold";

export async function executeReusableSuite(options: {
  suiteFile: string;
  scopeFile: string;
  runner?: NativeEngineRunner;
}) {
  const suite = await readReusableSuite(options.suiteFile);
  const scope = scopeSchema.parse(await readFrozenArtifact(options.scopeFile));
  if (
    scope.suiteFingerprint !== fingerprint(suite) ||
    fingerprint(scope.host) !== fingerprint(suite.host) ||
    scope.maximumCalls !== suite.limits.maximumCalls ||
    scope.phase !== suite.phase ||
    scope.experiment !== suite.experiment
  )
    throw new Error("A newly approved exact run scope is required.");
  await authorizeFixedRun({ engine: suite.host.engine });
  await requireProduct(suite.product);
  if (
    suite.experiment === "learning" &&
    suite.phase !== "preflight" &&
    (suite.learning.length !== 3 || suite.learning.some((preparation) => !preparation.completed))
  )
    throw new Error(
      "Learning infrastructure is incomplete; retain preparations and do not qualify.",
    );
  console.log(
    `Native invocation ceiling: ${suite.limits.maximumCalls} (${suite.limits.candidateCalls} planned + ${suite.limits.retryCalls} reserved retries); prior shared preparation ceiling ${suite.limits.preparationCalls}.`,
  );
  const directory = path.dirname(options.suiteFile);
  const release = await lockEvaluation(directory);
  try {
    const validation = await validateReusableSuite(options.suiteFile);
    if (!validation.passed) throw new Error("Offline validation failed. No model calls made.");
    const receiptFile = path.join(directory, "receipt.json");
    const exists = await Bun.file(receiptFile).exists();
    let receipt: Receipt = exists
      ? recoverReceipt({
          suite,
          receipt: receiptSchema.parse(await readFrozenArtifact(receiptFile)),
        })
      : {
          protocol: "preference-respect-v3",
          suiteFingerprint: fingerprint(suite),
          status: "running",
          cells: matrixCells(suite),
        };
    const budgetFile = path.join(directory, "budget.json");
    if (await Bun.file(budgetFile).exists()) {
      const ledger = budgetSchema.parse(JSON.parse(await Bun.file(budgetFile).text()));
      if (!exists || ledger.maximumCalls !== suite.limits.maximumCalls)
        throw new Error(
          "Retain the existing budget; its receipt or frozen ceiling is inconsistent.",
        );
    }
    const budget = await evaluationBudget({
      directory,
      resume: exists,
      maximumCalls: suite.limits.maximumCalls,
    });
    const persist = () => writeFrozenArtifact({ file: receiptFile, value: receipt });
    await persist();
    const pauseFile = path.join(directory, "provider-pause.json");
    const holdFile = path.join(directory, "infrastructure-hold.json");
    for (const cell of receipt.cells) {
      if (await Bun.file(pauseFile).exists()) return { receiptFile, paused: true, pauseFile };
      if (await Bun.file(holdFile).exists()) return { receiptFile, paused: true, holdFile };
      await requireProduct(suite.product);
      const entry = suite.cases.find((candidate) => candidate.task.id === cell.caseId);
      if (!entry) throw new Error("Missing fixed case.");
      if (cell.attempts.length > 0 && !retryEligible(cell)) continue;
      do {
        const attempt: Attempt = {
          number: cell.attempts.length === 0 ? 1 : 2,
          status: "running",
          calls: 0,
          record: null,
          diagnostics: [],
          checks: [],
        };
        cell.attempts.push(attempt);
        await persist();
        const outputDirectory = path.join(
          directory,
          "attempts",
          cell.caseId,
          cell.setup,
          String(cell.repetition),
          String(attempt.number),
        );
        await mkdir(outputDirectory, { recursive: true, mode: 0o700 });
        const diagnostic = async (value: Attempt["diagnostics"][number]) => {
          attempt.diagnostics.push(value);
          await persist();
        };
        const reservation = {
          reserve: async () => {
            const remaining = await budget.reserve();
            attempt.calls += 1;
            await persist();
            return remaining;
          },
          settle: budget.settle,
        };
        try {
          const record = await runStudySession({
            suite: nativeSuite({ suite, cases: [entry] }),
            task: entry.task,
            arm: nativeSetups[cell.setup],
            repeat: cell.repetition,
            runner: options.runner ?? runNativeEngine,
            budget: reservation,
            outputDirectory,
            deadlineAt: Date.now() + 30 * 60 * 1000,
            guidance: selectedEnvironment({
              suite,
              setup: cell.setup,
              case: entry,
              repetition: cell.repetition,
            }),
            blockedPaths: [
              path.resolve(import.meta.dir, "../../.."),
              path.dirname(suite.privateBundle),
              directory,
            ],
            onDiagnostic: diagnostic,
          });
          attempt.record = {
            ...record,
            productCommit: suite.product.commit,
            productTreeFingerprint: suite.product.tree,
            correctness: gradeCorrectness({ case: entry, record }),
          };
          attempt.checks = gradeCase({ case: entry, record });
          if (suite.experiment === "routing")
            attempt.checks.push(routingSelection({ caseId: entry.task.id, record }));
        } catch (error) {
          if (attempt.diagnostics.length === 0)
            await diagnostic(nativeFailure({ stage: "setup", error }));
          attempt.record = {
            ...pendingRun({
              arm: nativeSetups[cell.setup],
              taskId: cell.caseId,
              repeat: cell.repetition,
            }),
            status: "error",
            error: "Native attempt failed; inspect private diagnostics.",
          };
        }
        attempt.status = "complete";
        const providerPause = attempt.record ? confirmedProviderPause(attempt.record) : null;
        if (providerPause) attempt.diagnostics.push(providerPause);
        await persist();
        console.log(
          `${cell.setup} ${cell.caseId} repetition ${cell.repetition + 1} attempt ${attempt.number}: ${attempt.record?.status ?? "error"}`,
        );
        if (providerPause) {
          await writeFrozenArtifact({
            file: pauseFile,
            value: {
              host: suite.host,
              observedAt: new Date().toISOString(),
              diagnostic: providerPause,
            },
          });
          return { receiptFile, paused: true, pauseFile };
        }
        const infrastructure = unresolvedInfrastructure(cell);
        if (infrastructure) {
          await writeFrozenArtifact({
            file: holdFile,
            value: {
              host: suite.host,
              observedAt: new Date().toISOString(),
              caseId: cell.caseId,
              setup: cell.setup,
              repetition: cell.repetition,
              diagnostic: infrastructure,
            },
          });
          return { receiptFile, paused: true, holdFile };
        }
      } while (retryEligible(cell));
    }
    receipt = { ...receipt, status: "complete" };
    await persist();
    await requireProduct(suite.product);
    const ledger = budgetSchema.parse(
      JSON.parse(await Bun.file(path.join(directory, "budget.json")).text()),
    );
    return {
      receiptFile,
      attempts: receipt.cells.reduce((total, cell) => total + cell.attempts.length, 0),
      calls: ledger.calls,
    };
  } finally {
    await release();
  }
}
