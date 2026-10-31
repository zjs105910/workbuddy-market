import { mkdir } from "node:fs/promises";
import path from "node:path";
import { z } from "zod";
import { ownedWrite } from "@shadowclone/core";
import { requirePrivateDirectory, treeFingerprint } from "../native/files";
import { studySuiteSchema } from "../native/study/schema";
import { fixedDefinition, benchmarkFingerprint, internalArms } from "./definition";
import { fixedArmEnvironments } from "./arms";
import { fixedCliVersion, fixedGraderFingerprint, fixedProductIdentity, fixedRuntime } from "./identity";
import { fingerprint } from "../shared/structured";
import type { NativeEngine } from "@shadowclone/agents";

export const fixedSuiteSchema = z.strictObject({
  protocol: z.literal("preference-respect-v1"),
  version: z.literal(1),
  benchmark: z.literal("engineering-preferences-v1"),
  benchmarkFingerprint: z.string().length(64),
  graderFingerprint: z.string().length(64),
  runtime: z.strictObject({ bun: z.string(), typescript: z.string() }),
  branch: z.string(),
  suite: studySuiteSchema,
});

export type FixedSuite = z.infer<typeof fixedSuiteSchema>;
export type PrepareFixedOptions = {
  directory: string; engine: NativeEngine; model: string; effort: "medium" | "high"; repetitions: number;
  cliVersion?: string;
};

export async function prepareFixedSuite(options: PrepareFixedOptions): Promise<string> {
  const directory = await requirePrivateDirectory(options.directory);
  await mkdir(directory, { recursive: true, mode: 0o700 });
  const suiteFile = path.join(directory, "suite.json");
  if (await Bun.file(suiteFile).exists()) throw new Error("Preparation needs a new directory; use the existing suite to resume");
  const product = await fixedProductIdentity();
  const cliVersion = options.cliVersion ?? await fixedCliVersion(options.engine);
  const templateDirectory = path.join(directory, "template");
  await mkdir(templateDirectory, { mode: 0o700 });
  await ownedWrite({ path: path.join(templateDirectory, "AGENTS.md"), content: fixedDefinition.repositoryInstructions });
  if (options.engine === "claude-code") await ownedWrite({ path: path.join(templateDirectory, "CLAUDE.md"), content: "@AGENTS.md\n" });
  const suite = studySuiteSchema.parse({
    protocol: "preference-study-v1", version: 1, studyId: crypto.randomUUID(),
    productCommit: product.commit, productTreeFingerprint: product.tree,
    templateDirectory, templateFingerprint: await treeFingerprint(templateDirectory),
    cliVersion, engine: options.engine, model: options.model, effort: options.effort,
    keyItems: fixedDefinition.profile, wizardBuild: ["handwritten-profile"],
    resolutionRule: "Current requests override personal defaults; shared repository requirements remain authoritative.",
    arms: await fixedArmEnvironments({ directory, engine: options.engine }), memory: [], tasks: fixedDefinition.tasks, droppedChecks: [],
    analysis: { repetitions: options.repetitions, bootstrapSeed: 20261001, bootstrapSamples: 10000 },
    limits: { maximumCalls: fixedDefinition.tasks.reduce((total, task) => total + task.turns.length, 0) * internalArms.length * options.repetitions,
      concurrency: 1, codeTurnSeconds: 240, adviceTurnSeconds: 120, judgeSeconds: 60 },
  });
  const frozen = fixedSuiteSchema.parse({ protocol: "preference-respect-v1", version: 1, benchmark: fixedDefinition.name,
    benchmarkFingerprint, graderFingerprint: await fixedGraderFingerprint(), runtime: fixedRuntime, branch: product.branch, suite });
  await ownedWrite({ path: suiteFile, content: JSON.stringify(frozen, null, 2) });
  await ownedWrite({ path: path.join(directory, "freeze.json"), content: JSON.stringify({ fingerprint: fingerprint(frozen) }) });
  await ownedWrite({ path: path.join(directory, "native-suite.json"), content: JSON.stringify(suite, null, 2) });
  return suiteFile;
}

export async function readFixedSuite(suiteFile: string): Promise<FixedSuite> {
  await requirePrivateDirectory(path.dirname(suiteFile));
  const frozen = fixedSuiteSchema.parse(JSON.parse(await Bun.file(suiteFile).text()));
  const saved = z.strictObject({ fingerprint: z.string().length(64) }).parse(JSON.parse(await Bun.file(path.join(path.dirname(suiteFile), "freeze.json")).text()));
  if (saved.fingerprint !== fingerprint(frozen)) throw new Error("Frozen inputs changed; start a new run");
  if (fingerprint(frozen.runtime) !== fingerprint(fixedRuntime)) throw new Error("Evaluation runtime changed after preparation");
  if (frozen.graderFingerprint !== await fixedGraderFingerprint() || frozen.benchmarkFingerprint !== benchmarkFingerprint || fingerprint(frozen.suite.tasks) !== fingerprint(fixedDefinition.tasks) ||
    fingerprint(frozen.suite.keyItems) !== fingerprint(fixedDefinition.profile) || frozen.suite.droppedChecks.length > 0) {
    throw new Error("Fixed benchmark changed; start a new versioned run");
  }
  for (const arm of Object.values(frozen.suite.arms)) {
    if (arm.fingerprint !== fingerprint(arm.files)) throw new Error("Frozen guidance fingerprint does not match its files");
  }
  const native = studySuiteSchema.parse(JSON.parse(await Bun.file(path.join(path.dirname(suiteFile), "native-suite.json")).text()));
  if (fingerprint(native) !== fingerprint(frozen.suite)) throw new Error("Native suite changed after preparation");
  return frozen;
}
