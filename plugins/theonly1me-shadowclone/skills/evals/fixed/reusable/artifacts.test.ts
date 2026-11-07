import { expect, test } from "bun:test";
import { mkdir, mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fixtureSuite } from "./testFixtures";
import { readReusableSuite, invocationCeiling } from "./freeze";
import { developmentCases, benchmarkFingerprint } from "./definition";
import { graderFingerprint } from "./identity";
import { publishedHeldout } from "./seal";
import { treeFingerprint } from "../../native/files";
import { fixedRuntime } from "../identity";
import { writeFrozenArtifact } from "../workflow/preparation";

test("development remains sealed from held-out contents and stale inputs cannot resume", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "v3-artifact-"));
  try {
    const suite = fixtureSuite({ cases: developmentCases });
    suite.phase = "development";
    suite.templateDirectory = path.join(directory, "template");
    await mkdir(suite.templateDirectory, { mode: 0o700 });
    await Bun.write(
      path.join(suite.templateDirectory, "AGENTS.md"),
      "Synthetic repository requirements.\n",
    );
    suite.templateFingerprint = await treeFingerprint(suite.templateDirectory);
    suite.privateBundle = path.join(directory, "sealed-bundle-does-not-exist.json");
    suite.bundleFingerprint = publishedHeldout.fingerprint;
    suite.benchmarkFingerprint = benchmarkFingerprint;
    suite.graderFingerprint = await graderFingerprint();
    suite.runtime = fixedRuntime;
    const ceiling = invocationCeiling({
      cases: suite.cases,
      experiment: "learning",
      preparationCalls: 48,
    });
    suite.limits = {
      preparationCalls: 48,
      candidateCalls: ceiling.candidateCalls,
      retryCalls: ceiling.retryCalls,
      maximumCalls: ceiling.maximumCalls,
      codeSeconds: 240,
      adviceSeconds: 120,
    };
    const file = path.join(directory, "suite.json");
    await writeFrozenArtifact({ file, value: suite });
    expect((await readReusableSuite(file)).cases).toHaveLength(16);
    const stale = { ...suite, graderFingerprint: "f".repeat(64) };
    await writeFrozenArtifact({ file, value: stale });
    await expect(readReusableSuite(file)).rejects.toThrow("stale");
    await writeFrozenArtifact({ file, value: suite });
    await Bun.write(
      path.join(suite.templateDirectory, "new-untracked.txt"),
      "A changed workspace input.",
    );
    await expect(readReusableSuite(file)).rejects.toThrow("template changed");
    await Bun.write(file, JSON.stringify({ ...suite, repetitions: 2 }));
    await expect(readReusableSuite(file)).rejects.toThrow("artifact changed");
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
