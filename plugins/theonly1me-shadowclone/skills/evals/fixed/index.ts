import { mkdir } from "node:fs/promises";
import path from "node:path";
import { readManagedPolicy, projectPaths, ownedWrite } from "@shadowclone/core";
import { requirePrivateDirectory, treeFingerprint } from "../native/files";
import { matrixReceiptSchema } from "../native/study/matrix";
import { runStudy } from "../native/study/phases";
import { validateFixtures } from "../native/study/validate";
import { internalArms } from "./definition";
import { validateFixedGraders } from "./calibration";
import { readFixedSuite } from "./freeze";
import { fixedProductIdentity } from "./identity";
import { fixedReport, fixedReportSchema, compareFixedReports } from "./report";
import type { NativeEngine, NativeEngineRunner } from "@shadowclone/agents";
import type { ManagedPolicy } from "@shadowclone/core";

export { prepareFixedSuite } from "./freeze";

export async function authorizeFixedRun(options: { engine: NativeEngine; managedConfigPath?: string | null }): Promise<void> {
  const policy = await readManagedPolicy(options.managedConfigPath === undefined ? projectPaths.managedConfigFile : options.managedConfigPath);
  requireFixedPolicy({ engine: options.engine, policy });
}

export function requireFixedPolicy(options: { engine: NativeEngine; policy: ManagedPolicy }): void {
  if (!options.policy.enabled || !options.policy.allowedEngines.includes(options.engine) || options.policy.maxActionTier !== "act") {
    throw new Error("Managed policy does not permit this native coding evaluation");
  }
}

export async function validateFixedSuite(suiteFile: string) {
  const frozen = await readFixedSuite(suiteFile);
  if (await treeFingerprint(frozen.suite.templateDirectory) !== frozen.suite.templateFingerprint) throw new Error("Fixed template changed after preparation");
  const directory = await requirePrivateDirectory(path.join(path.dirname(suiteFile), "validation"));
  await mkdir(directory, { recursive: true, mode: 0o700 });
  const graders = validateFixedGraders();
  const fixtures = await validateFixtures({ suite: frozen.suite, outputDirectory: directory });
  const result = { passed: graders.passed && fixtures.passed, graders, fixtures };
  await ownedWrite({ path: path.join(directory, "result.json"), content: JSON.stringify(result, null, 2) });
  return result;
}

export async function runFixedSuite(options: { suiteFile: string; runner?: NativeEngineRunner }) {
  const frozen = await readFixedSuite(options.suiteFile);
  await authorizeFixedRun({ engine: frozen.suite.engine });
  const requireProduct = async () => {
    const product = await fixedProductIdentity();
    if (product.commit !== frozen.suite.productCommit || product.tree !== frozen.suite.productTreeFingerprint) throw new Error("Product changed after preparation; start a new run");
  };
  await requireProduct();
  const validation = await validateFixedSuite(options.suiteFile);
  if (!validation.passed) throw new Error("Fixed fixture or grader validation failed; no model calls were made");
  const directory = path.dirname(options.suiteFile);
  await runStudy({ suiteFile: path.join(directory, "native-suite.json"), outputDirectory: directory, arms: internalArms, runner: options.runner,
    writeLine: (line) => console.log(line.replace(/^original /, "profile ").replace(/^first-time /, "shadowclone ")) });
  await requireProduct();
  return reportFixedSuite(options.suiteFile);
}

export async function reportFixedSuite(suiteFile: string) {
  const frozen = await readFixedSuite(suiteFile);
  const directory = path.dirname(suiteFile);
  const receipt = matrixReceiptSchema.parse(JSON.parse(await Bun.file(path.join(directory, "scored", "receipt.json")).text()));
  const report = fixedReport({ frozen, receipt });
  await ownedWrite({ path: path.join(directory, "report.json"), content: JSON.stringify(report, null, 2) });
  return report;
}

export async function compareFixedRuns(options: { baselineFile: string; candidateFile: string }) {
  for (const filePath of [options.baselineFile, options.candidateFile]) await requirePrivateDirectory(path.dirname(filePath));
  const baseline = fixedReportSchema.parse(JSON.parse(await Bun.file(options.baselineFile).text()));
  const candidate = fixedReportSchema.parse(JSON.parse(await Bun.file(options.candidateFile).text()));
  return compareFixedReports({ baseline, candidate });
}
