import { mkdir, readdir } from "node:fs/promises";
import path from "node:path";
import { ownedWrite } from "@shadowclone/core";
import { requirePrivateDirectory, treeFingerprint } from "../../native/files";
import { fingerprint } from "../../shared/structured";
import { fixedCliVersion, fixedProductIdentity, fixedRuntime } from "../identity";
import { workflowBenchmarkFingerprint } from "./definition";
import { captureStartingEnvironments, initializeRouting, materializeCorrections, writeExistingLibrary } from "./environment";
import { workflowGraderFingerprint } from "./identity";
import { workflowLayout, captureWorkflowArm } from "./layout";
import { workflowPreparationSchema, type LearnerConfiguration, type WorkflowPreparation } from "./schema";

export async function writeFrozenArtifact(options: { file: string; value: unknown }) {
  await ownedWrite({ path: options.file, content: JSON.stringify(options.value, null, 2) });
  await ownedWrite({ path: `${options.file}.fingerprint`, content: fingerprint(options.value) });
}

export async function readFrozenArtifact(file: string): Promise<unknown> {
  await requirePrivateDirectory(path.dirname(file));
  const value: unknown = JSON.parse(await Bun.file(file).text());
  if (await Bun.file(`${file}.fingerprint`).text() !== fingerprint(value)) throw new Error("Frozen evaluation artifact changed");
  return value;
}

export async function prepareWorkflowEnvironments(options: {
  directory: string; engine: LearnerConfiguration["engine"]; model: string; effort: LearnerConfiguration["effort"];
  maximumCalls: number; cliVersion?: string;
}) {
  const directory = await requirePrivateDirectory(options.directory);
  await mkdir(directory, { recursive: true, mode: 0o700 });
  if ((await readdir(directory)).length > 0) throw new Error("Environment preparation requires an empty private directory");
  const layout = workflowLayout(directory);
  const learner = workflowPreparationSchema.shape.learner.parse({ engine: options.engine, model: options.model, effort: options.effort,
    maximumCalls: options.maximumCalls, cliVersion: options.cliVersion ?? await fixedCliVersion(options.engine), callSeconds: 120, deadlineSeconds: 1200 });
  const product = await fixedProductIdentity();
  for (const arm of ["original", "routing", "deep"]) {
    await writeExistingLibrary({ directory, arm });
    if (arm !== "original") await initializeRouting({ directory, arm });
  }
  await materializeCorrections(directory);
  const preparation = workflowPreparationSchema.parse({ protocol: "preference-respect-v2", version: 2, product,
    runtime: fixedRuntime, benchmarkFingerprint: workflowBenchmarkFingerprint, graderFingerprint: await workflowGraderFingerprint(), learner,
    corpusFingerprint: await treeFingerprint(layout.paths("deep").claudeProjectsDirectory),
    learningStateFingerprint: await treeFingerprint(layout.paths("deep").shadowcloneDirectory), starting: await captureStartingEnvironments(directory) });
  await writeFrozenArtifact({ file: layout.preparation, value: preparation });
  return layout.preparation;
}

export async function requireWorkflowDefinition(preparation: WorkflowPreparation) {
  if (preparation.benchmarkFingerprint !== workflowBenchmarkFingerprint || preparation.graderFingerprint !== await workflowGraderFingerprint() ||
    fingerprint(preparation.runtime) !== fingerprint(fixedRuntime)) throw new Error("Benchmark, grader, or runtime changed; prepare a new run");
}

export async function requireWorkflowProduct(preparation: WorkflowPreparation) {
  const product = await fixedProductIdentity();
  if (product.commit !== preparation.product.commit || product.tree !== preparation.product.tree) throw new Error("Product changed after preparation; prepare a new run");
}

export async function readWorkflowPreparation(file: string) {
  const preparation = workflowPreparationSchema.parse(await readFrozenArtifact(file));
  await requireWorkflowDefinition(preparation);
  return preparation;
}

export async function requirePreparationInputs(options: { directory: string; preparation: WorkflowPreparation; beforeLearning: boolean }) {
  const layout = workflowLayout(options.directory);
  if (await treeFingerprint(layout.paths("deep").claudeProjectsDirectory) !== options.preparation.corpusFingerprint) throw new Error("Synthetic correction corpus changed after preparation");
  if (options.beforeLearning && await treeFingerprint(layout.paths("deep").shadowcloneDirectory) !== options.preparation.learningStateFingerprint) throw new Error("Private learning configuration or state changed after preparation");
  for (const engine of ["codex", "claude-code"] as const) {
    for (const arm of ["original", "routing", ...(options.beforeLearning ? ["deep"] : [])]) {
      const actual = await captureWorkflowArm({ directory: options.directory, arm, engine });
      const expected = arm === "original" ? options.preparation.starting[engine].original : options.preparation.starting[engine]["first-time"];
      if (fingerprint(actual) !== fingerprint(expected)) throw new Error("Starting guidance changed after preparation");
    }
  }
}
