import { expect, test } from "bun:test";
import { mkdir, mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { budgetSchema, evaluationBudget } from "../../shared/accounting";
import { treeFingerprint } from "../../native/files";
import { fixedRuntime } from "../identity";
import { writeFrozenArtifact } from "../workflow/preparation";
import { benchmarkFingerprint, developmentCases } from "./definition";
import { graderFingerprint } from "./identity";
import { publishedHeldout } from "./seal";
import { fixtureReceipt, fixtureSuite } from "./testFixtures";
import { reportReusableSuite } from "./report";

test("reporting reads the real mutable budget ledger without a frozen-artifact sidecar", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "v3-ledger-report-"));
  try {
    const templateDirectory = path.join(directory, "template");
    await mkdir(templateDirectory, { mode: 0o700 });
    await Bun.write(
      path.join(templateDirectory, "AGENTS.md"),
      "Synthetic repository requirements.\n",
    );
    const suite = fixtureSuite({ cases: developmentCases });
    suite.phase = "preflight";
    suite.repetitions = 1;
    suite.benchmarkFingerprint = benchmarkFingerprint;
    suite.graderFingerprint = await graderFingerprint();
    suite.bundleFingerprint = publishedHeldout.fingerprint;
    suite.runtime = fixedRuntime;
    suite.templateDirectory = templateDirectory;
    suite.templateFingerprint = await treeFingerprint(templateDirectory);
    suite.limits = {
      ...suite.limits,
      preparationCalls: 0,
      candidateCalls: 32,
      retryCalls: 32,
      maximumCalls: 64,
    };
    const receipt = fixtureReceipt(suite);
    const suiteFile = path.join(directory, "suite.json");
    await writeFrozenArtifact({ file: suiteFile, value: suite });
    await writeFrozenArtifact({ file: path.join(directory, "receipt.json"), value: receipt });
    const budget = await evaluationBudget({
      directory,
      resume: false,
      maximumCalls: suite.limits.maximumCalls,
    });
    for (const cell of receipt.cells) {
      expect(cell.attempts[0]?.calls).toBe(1);
      await budget.reserve();
      await budget.settle(0);
    }
    expect(await Bun.file(path.join(directory, "budget.json.fingerprint")).exists()).toBe(false);
    await expect(reportReusableSuite(suiteFile)).resolves.toMatchObject({
      status: "complete",
      calls: 32,
      scores: [
        { setup: "bare", score: 1 },
        { setup: "told", score: 1 },
      ],
    });
    expect(await Bun.file(path.join(directory, "report.json.fingerprint")).exists()).toBe(true);
    const ledger = budgetSchema.parse(await Bun.file(path.join(directory, "budget.json")).json());
    await Bun.write(path.join(directory, "budget.json"), JSON.stringify({ ...ledger, calls: 31 }));
    await expect(reportReusableSuite(suiteFile)).rejects.toThrow("Invocation ledger conflicts");
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
