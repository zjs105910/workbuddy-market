import { mkdir, readdir } from "node:fs/promises";
import path from "node:path";
import { z } from "zod";
import { ownedWrite } from "@shadowclone/core";
import { requirePrivateDirectory, treeFingerprint } from "../../native/files";
import { studySuiteSchema } from "../../native/study/schema";
import { fingerprint } from "../../shared/structured";
import { fixedCliVersion } from "../identity";
import { workflowDefinition, workflowInternalArms } from "./definition";
import { preparedEnvironmentsSchema } from "./schema";
import { readPreparedEnvironments } from "./learning";
import { readFrozenArtifact, writeFrozenArtifact, requireWorkflowDefinition, requireWorkflowProduct } from "./preparation";
import type { NativeEngine } from "@shadowclone/agents";

export const workflowSuiteSchema = z.strictObject({ protocol: z.literal("preference-respect-v2"), version: z.literal(2),
  environments: preparedEnvironmentsSchema, suite: studySuiteSchema });
export type WorkflowSuite = z.infer<typeof workflowSuiteSchema>;

export async function prepareWorkflowSuite(options: {
  directory: string; environmentsFile: string; engine: NativeEngine; model: string; effort: "medium" | "high"; repetitions: number; cliVersion?: string;
}) {
  const environments = await readPreparedEnvironments(options.environmentsFile);
  await requireWorkflowProduct(environments.preparation);
  const directory = await requirePrivateDirectory(options.directory);
  await mkdir(directory, { recursive: true, mode: 0o700 });
  if ((await readdir(directory)).length > 0) throw new Error("Scored preparation requires an empty private directory");
  const templateDirectory = path.join(directory, "template");
  await mkdir(templateDirectory, { mode: 0o700 });
  await ownedWrite({ path: path.join(templateDirectory, "AGENTS.md"), content: workflowDefinition.repositoryInstructions });
  if (options.engine === "claude-code") await ownedWrite({ path: path.join(templateDirectory, "CLAUDE.md"), content: "@AGENTS.md\n" });
  const suite = studySuiteSchema.parse({ protocol: "preference-study-v1", version: 1, studyId: crypto.randomUUID(),
    productCommit: environments.preparation.product.commit, productTreeFingerprint: environments.preparation.product.tree,
    templateDirectory, templateFingerprint: await treeFingerprint(templateDirectory), engine: options.engine,
    cliVersion: options.cliVersion ?? await fixedCliVersion(options.engine), model: options.model, effort: options.effort,
    keyItems: workflowDefinition.profile, wizardBuild: ["synthetic-existing-skills"], memory: [],
    resolutionRule: "Current requests override personal defaults; shared repository requirements remain authoritative.",
    arms: environments.engines[options.engine], tasks: workflowDefinition.tasks, droppedChecks: [],
    analysis: { repetitions: options.repetitions, bootstrapSeed: 20261001, bootstrapSamples: 10000 },
    limits: { maximumCalls: workflowDefinition.tasks.reduce((total, task) => total + task.turns.length, 0) * workflowInternalArms.length * options.repetitions,
      concurrency: 1, codeTurnSeconds: 240, adviceTurnSeconds: 120, judgeSeconds: 60 } });
  const frozen = workflowSuiteSchema.parse({ protocol: "preference-respect-v2", version: 2, environments, suite });
  const suiteFile = path.join(directory, "suite.json");
  await writeFrozenArtifact({ file: suiteFile, value: frozen });
  await ownedWrite({ path: path.join(directory, "native-suite.json"), content: JSON.stringify(suite, null, 2) });
  return suiteFile;
}

export async function readWorkflowSuite(file: string) {
  const frozen = workflowSuiteSchema.parse(await readFrozenArtifact(file));
  await requireWorkflowDefinition(frozen.environments.preparation);
  if (frozen.environments.learning.outcome !== "complete" || frozen.environments.preparationFingerprint !== fingerprint(frozen.environments.preparation) ||
    fingerprint(frozen.suite.arms) !== fingerprint(frozen.environments.engines[frozen.suite.engine]) ||
    frozen.suite.productCommit !== frozen.environments.preparation.product.commit || frozen.suite.productTreeFingerprint !== frozen.environments.preparation.product.tree ||
    fingerprint(frozen.suite.tasks) !== fingerprint(workflowDefinition.tasks) || fingerprint(frozen.suite.keyItems) !== fingerprint(workflowDefinition.profile) ||
    frozen.suite.droppedChecks.length > 0) throw new Error("Frozen benchmark inputs are inconsistent");
  const native = studySuiteSchema.parse(JSON.parse(await Bun.file(path.join(path.dirname(file), "native-suite.json")).text()));
  if (fingerprint(native) !== fingerprint(frozen.suite)) throw new Error("Native suite changed after freezing");
  return frozen;
}
