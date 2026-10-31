import { mkdir } from "node:fs/promises";
import path from "node:path";
import { ownedWrite } from "@shadowclone/core";
import { requirePrivateDirectory, treeFingerprint } from "../../native/files";
import { matrixReceiptSchema } from "../../native/study/matrix";
import { runStudy } from "../../native/study/phases";
import { validateFixtures } from "../../native/study/validate";
import { authorizeFixedRun } from "../index";
import { validateFixedGraders } from "../calibration";
import { readWorkflowSuite } from "./freeze";
import { requireWorkflowProduct } from "./preparation";
import { workflowInternalArms } from "./definition";
import { workflowReport, workflowReportSchema, compareWorkflowReports } from "./report";
import type { NativeEngineRunner } from "@shadowclone/agents";

export { prepareWorkflowEnvironments } from "./preparation";
export { learnWorkflowEnvironments } from "./learning";
export { prepareWorkflowSuite } from "./freeze";

export async function validateWorkflowSuite(suiteFile: string) {
  const frozen = await readWorkflowSuite(suiteFile);
  if (await treeFingerprint(frozen.suite.templateDirectory) !== frozen.suite.templateFingerprint) throw new Error("Fixed template changed after preparation");
  const directory = await requirePrivateDirectory(path.join(path.dirname(suiteFile), "validation"));
  await mkdir(directory, { recursive: true, mode: 0o700 });
  const graders = validateFixedGraders();
  const fixtures = await validateFixtures({ suite: frozen.suite, outputDirectory: directory });
  const result = { passed: graders.passed && fixtures.passed, graders, fixtures };
  await ownedWrite({ path: path.join(directory, "result.json"), content: JSON.stringify(result, null, 2) });
  return result;
}

export async function runWorkflowSuite(options: { suiteFile: string; runner?: NativeEngineRunner }) {
  const frozen = await readWorkflowSuite(options.suiteFile);
  await authorizeFixedRun({ engine: frozen.suite.engine });
  await requireWorkflowProduct(frozen.environments.preparation);
  const validation = await validateWorkflowSuite(options.suiteFile);
  if (!validation.passed) throw new Error("Fixture or grader validation failed; no scored model calls were made");
  const directory = path.dirname(options.suiteFile);
  await runStudy({ suiteFile: path.join(directory, "native-suite.json"), outputDirectory: directory, arms: workflowInternalArms, runner: options.runner,
    writeLine: line => console.log(line.replace(/^original /, "skills ").replace(/^first-time /, "routing ")) });
  await requireWorkflowProduct(frozen.environments.preparation);
  return reportWorkflowSuite(options.suiteFile);
}

export async function reportWorkflowSuite(suiteFile: string) {
  const frozen = await readWorkflowSuite(suiteFile);
  const directory = path.dirname(suiteFile);
  const receipt = matrixReceiptSchema.parse(JSON.parse(await Bun.file(path.join(directory, "scored/receipt.json")).text()));
  const report = workflowReport({ frozen, receipt });
  await ownedWrite({ path: path.join(directory, "report.json"), content: JSON.stringify(report, null, 2) });
  return report;
}

export async function compareWorkflowRuns(options: { baselineFile: string; candidateFile: string }) {
  for (const file of [options.baselineFile, options.candidateFile]) await requirePrivateDirectory(path.dirname(file));
  const baseline = workflowReportSchema.parse(JSON.parse(await Bun.file(options.baselineFile).text()));
  const candidate = workflowReportSchema.parse(JSON.parse(await Bun.file(options.candidateFile).text()));
  return compareWorkflowReports({ baseline, candidate });
}
