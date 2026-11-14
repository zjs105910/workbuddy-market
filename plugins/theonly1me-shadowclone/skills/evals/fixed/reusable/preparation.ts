import { mkdir, readdir } from "node:fs/promises";
import path from "node:path";
import { z } from "zod";
import { armEnvironmentSchema } from "../../native/study/schema";
import { requirePrivateDirectory, treeFingerprint } from "../../native/files";
import { fingerprint } from "../../shared/structured";
import { fixedCliVersion, fixedProductIdentity, fixedRuntime } from "../identity";
import { readFrozenArtifact, writeFrozenArtifact } from "../workflow/preparation";
import { benchmarkFingerprint } from "./definition";
import {
  prepareManualEnvironment,
  materializeCorpus,
  captureEnvironment,
  reusableLayout,
  requireManualPreserved,
} from "./environments";
import { graderFingerprint } from "./identity";
import { environmentSetSchema, identitySchema } from "./schema";
import { learnerSchema } from "../workflow/schema";
import { publishedHeldout, requireCaseReview } from "./seal";
import { validateCorpusScope } from "./corpusScope";
import { writeLearningSource } from "./learningSource";

export const preparationSchema = z.strictObject({
  protocol: z.literal("preference-respect-v3"),
  id: z.uuid(),
  product: identitySchema,
  runtime: z.strictObject({ bun: z.string(), typescript: z.string() }),
  benchmarkFingerprint: z.string(),
  graderFingerprint: z.string(),
  bundleFile: z.string(),
  bundleFingerprint: z.string(),
  reviewFile: z.string(),
  reviewFingerprint: z.string(),
  learner: learnerSchema.extend({ engine: z.literal("codex") }),
  environments: z.record(
    z.enum(["codex", "claude-code"]),
    z.record(z.enum(["atlas", "boreal"]), environmentSetSchema),
  ),
  routingEnvironments: z.record(
    z.enum(["codex", "claude-code"]),
    z.strictObject({ skills: armEnvironmentSchema, routing: armEnvironmentSchema }),
  ),
  inputs: z.array(z.strictObject({ corpus: z.string(), state: z.string() })).length(3),
  maximumCalls: z.number().int().positive(),
});
export const preparationScopeSchema = z.strictObject({
  preparationFingerprint: z.string(),
  learner: learnerSchema.extend({ engine: z.literal("codex") }),
  maximumCalls: z.number().int().positive(),
  decision: z.literal("approved"),
});
export type Preparation = z.infer<typeof preparationSchema>;

export async function captureSets(directory: string): Promise<Preparation["environments"]> {
  const host = async (engine: "codex" | "claude-code") => {
    const repository = async (repository: "atlas" | "boreal") => {
      const capture = (arm: string) => captureEnvironment({ directory, engine, repository, arm });
      const skills = await capture("skills");
      const routing = await capture("routing");
      const told = await capture("told");
      const deep = await Promise.all([0, 1, 2].map((index) => capture(`deep-${index}`)));
      for (const environment of [routing, told])
        requireManualPreserved({ original: skills, candidate: environment });
      for (const environment of deep)
        requireManualPreserved({
          original: skills,
          candidate: environment,
          allowPublishedAdditions: true,
        });
      return { skills, routing, told, deep };
    };
    return { atlas: await repository("atlas"), boreal: await repository("boreal") };
  };
  return { codex: await host("codex"), "claude-code": await host("claude-code") };
}

export async function prepareReusableEnvironments(options: {
  directory: string;
  bundleFile: string;
  reviewFile: string;
  model: string;
  effort: "medium" | "high";
  maximumCalls?: number;
  cliVersion?: string;
}) {
  const review = await requireCaseReview(options);
  const directory = await requirePrivateDirectory(options.directory);
  await mkdir(directory, { recursive: true, mode: 0o700 });
  if ((await readdir(directory)).length > 0)
    throw new Error("Preparation requires an empty private directory.");
  const learner = learnerSchema.extend({ engine: z.literal("codex") }).parse({
    engine: "codex",
    model: options.model,
    effort: options.effort,
    maximumCalls: options.maximumCalls ?? 16,
    cliVersion: options.cliVersion ?? (await fixedCliVersion("codex")),
    callSeconds: 120,
    deadlineSeconds: 1200,
  });
  for (const arm of [
    "skills",
    "routing",
    "told",
    "deep-0",
    "deep-1",
    "deep-2",
    "library-skills",
    "library-routing",
  ]) {
    await prepareManualEnvironment({
      directory,
      arm,
      routed: !["skills", "library-skills"].includes(arm),
      told: arm === "told",
      routingLibrary: arm.startsWith("library-"),
    });
  }
  const corpusScope: Awaited<ReturnType<typeof validateCorpusScope>>[] = [];
  for (const preparation of [0, 1, 2]) {
    await materializeCorpus({ directory, preparation });
    corpusScope.push(await validateCorpusScope({ directory, preparation }));
  }
  const environments = await captureSets(directory);
  for (const host of Object.values(environments))
    for (const repository of Object.values(host)) {
      if (
        repository.deep.some(
          (environment) => fingerprint(environment) !== fingerprint(repository.routing),
        )
      )
        throw new Error("Deep preparations must start from identical routing guidance.");
    }
  const routingHost = async (engine: "codex" | "claude-code") => ({
    skills: await captureEnvironment({
      directory,
      arm: "library-skills",
      repository: "atlas",
      engine,
    }),
    routing: await captureEnvironment({
      directory,
      arm: "library-routing",
      repository: "atlas",
      engine,
    }),
  });
  const layout = reusableLayout(directory);
  const inputs = await Promise.all(
    [0, 1, 2].map(async (index) => ({
      corpus: await treeFingerprint(layout.paths(`deep-${index}`).claudeProjectsDirectory),
      state: await treeFingerprint(layout.paths(`deep-${index}`).shadowcloneDirectory),
    })),
  );
  const preparation = preparationSchema.parse({
    protocol: "preference-respect-v3",
    id: crypto.randomUUID(),
    product: await fixedProductIdentity(),
    runtime: fixedRuntime,
    benchmarkFingerprint,
    graderFingerprint: await graderFingerprint(),
    bundleFile: path.resolve(options.bundleFile),
    bundleFingerprint: publishedHeldout.fingerprint,
    reviewFile: path.resolve(options.reviewFile),
    reviewFingerprint: review.fingerprint,
    learner,
    environments,
    routingEnvironments: {
      codex: await routingHost("codex"),
      "claude-code": await routingHost("claude-code"),
    },
    inputs,
    maximumCalls: learner.maximumCalls * 3,
  });
  const preparationFile = path.join(directory, "preparation.json");
  await writeFrozenArtifact({ file: preparationFile, value: preparation });
  const sourceFile = await writeLearningSource({
    preparationFile,
    preparationFingerprint: fingerprint(preparation),
    product: preparation.product,
    repository: path.resolve(import.meta.dir, "../../.."),
  });
  return {
    preparationFile,
    sourceFile,
    corpusScope,
    fingerprint: fingerprint(preparation),
    invocationCeiling: {
      preparations: 3,
      callsEach: learner.maximumCalls,
      total: preparation.maximumCalls,
    },
    learner,
  };
}

export async function readPreparation(file: string) {
  const preparation = preparationSchema.parse(await readFrozenArtifact(file));
  if (
    preparation.benchmarkFingerprint !== benchmarkFingerprint ||
    preparation.graderFingerprint !== (await graderFingerprint()) ||
    fingerprint(preparation.runtime) !== fingerprint(fixedRuntime)
  )
    throw new Error("Frozen benchmark, graders, or runtime changed.");
  const review = await requireCaseReview({
    reviewFile: preparation.reviewFile,
    bundleFile: preparation.bundleFile,
  });
  if (review.fingerprint !== preparation.reviewFingerprint) throw new Error("Case review changed.");
  return preparation;
}

export async function requireProduct(product: Preparation["product"]) {
  const actual = await fixedProductIdentity();
  if (actual.commit !== product.commit || actual.tree !== product.tree)
    throw new Error("Product changed after preparation; create a new cohort.");
}

export async function authorizePreparations(options: {
  preparationFile: string;
  fingerprint: string;
}) {
  const preparation = await readPreparation(options.preparationFile);
  if (fingerprint(preparation) !== options.fingerprint)
    throw new Error("Preparation approval fingerprint differs.");
  const scope = preparationScopeSchema.parse({
    preparationFingerprint: options.fingerprint,
    learner: preparation.learner,
    maximumCalls: preparation.maximumCalls,
    decision: "approved",
  });
  const scopeFile = path.join(path.dirname(options.preparationFile), "learning-scope.json");
  await writeFrozenArtifact({ file: scopeFile, value: scope });
  return { scopeFile, invocationCeiling: scope.maximumCalls, learner: scope.learner };
}
