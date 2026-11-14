import path from "node:path";
import { z } from "zod";
import { runNativeEngine, type NativeEngineRunner } from "@shadowclone/agents";
import { ownedWrite } from "@shadowclone/core";
import { evaluationBudget } from "../../shared/accounting";
import { lockEvaluation } from "../../shared/lock";
import { requirePrivateDirectory } from "../files";
import { auditCoverage, coverageGate, transferVerifiedCoverage, type CoverageEntry } from "./coverage";
import { preparationLayout, preparationSchema, runPreparation, type PreparationStage } from "./prepare";
import { armEnvironmentSchema, keyItemSchema, personalArms, type PersonalArm } from "./schema";

export const keyFileSchema = z.strictObject({
  keyItems: z.array(keyItemSchema).min(4).max(40),
  wizardBuild: z.array(z.string().min(1)).min(1),
  resolutionRule: z.string().min(20).max(1000),
});

const armsFileSchema = z.strictObject({
  original: armEnvironmentSchema,
  "first-time": armEnvironmentSchema,
  deep: armEnvironmentSchema,
});

async function readJson(filePath: string): Promise<unknown> {
  return JSON.parse(await Bun.file(filePath).text());
}

export async function prepareStudyStage(options: {
  readonly preparationFile: string;
  readonly stage: PreparationStage;
}): Promise<unknown> {
  const preparation = preparationSchema.parse(await readJson(options.preparationFile));
  return runPreparation({ preparation, stage: options.stage });
}

export async function auditStudyCoverage(options: {
  readonly preparationFile: string;
  readonly keyFile: string;
  readonly runner?: NativeEngineRunner;
}): Promise<{ readonly coverage: Record<PersonalArm, CoverageEntry[]>; readonly gate: ReturnType<typeof coverageGate> }> {
  const preparation = preparationSchema.parse(await readJson(options.preparationFile));
  const key = keyFileSchema.parse(await readJson(options.keyFile));
  const directory = await requirePrivateDirectory(preparation.studyDirectory);
  const layout = preparationLayout(directory);
  const arms = armsFileSchema.parse(await readJson(layout.arms));
  const release = await lockEvaluation(directory);

  try {
    const budget = await evaluationBudget({
      directory, resume: await Bun.file(path.join(directory, "budget.json")).exists(), maximumCalls: preparation.maximumCalls,
    });
    const coverage: Record<PersonalArm, CoverageEntry[]> = { original: [], "first-time": [], deep: [] };

    for (const arm of personalArms) {
      coverage[arm] = await auditCoverage({
        arm, environment: arms[arm], keyItems: key.keyItems, runner: options.runner ?? runNativeEngine,
        budget, outputDirectory: directory, cliVersion: preparation.cliVersion,
      });
    }

    const transferred = transferVerifiedCoverage({ coverage, arms });
    const gate = coverageGate(transferred);
    await ownedWrite({ path: path.join(directory, "coverage.json"), content: JSON.stringify({ coverage: transferred, audited: coverage, gate }, null, 2) });
    return { coverage: transferred, gate };
  } finally {
    await release();
  }
}
