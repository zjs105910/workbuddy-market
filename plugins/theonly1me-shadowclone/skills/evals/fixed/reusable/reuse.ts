import path from "node:path";
import { fingerprint } from "../../shared/structured";
import { readInvocationLedger } from "./accounting";
import { readFrozenArtifact, writeFrozenArtifact } from "../workflow/preparation";
import { requireManualPreserved } from "./environments";
import { preparedSchema } from "./learning";
import { captureSets, preparationSchema, readPreparation, requireProduct } from "./preparation";
import { learningEvidenceSchema } from "./schema";
import { requireUnchangedLearningSource } from "./learningSource";
import { validateCorpusScope } from "./corpusScope";
export { learningSourceFiles, requireUnchangedLearningSource } from "./learningSource";

export async function reuseReusablePreparations(options: {
  sourceFile: string;
  preparationFile: string;
}) {
  const source = await requireUnchangedLearningSource({
    sourceFile: options.sourceFile,
    repository: path.resolve(import.meta.dir, "../../.."),
  });
  const original = preparationSchema.parse(await readFrozenArtifact(source.preparationFile));
  const preparation = await readPreparation(options.preparationFile);
  await requireProduct(preparation.product);
  if (
    fingerprint(original) !== source.preparationFingerprint ||
    fingerprint(original.product) !== fingerprint(source.product) ||
    original.benchmarkFingerprint !== preparation.benchmarkFingerprint ||
    original.bundleFingerprint !== preparation.bundleFingerprint ||
    fingerprint(original.runtime) !== fingerprint(preparation.runtime) ||
    fingerprint(original.learner) !== fingerprint(preparation.learner) ||
    fingerprint(original.environments) !== fingerprint(preparation.environments) ||
    fingerprint(original.routingEnvironments) !== fingerprint(preparation.routingEnvironments)
  )
    throw new Error("Cached learning inputs, baseline guidance, or learner differ.");
  const sourceDirectory = path.dirname(source.preparationFile);
  for (const index of [0, 1, 2]) {
    await validateCorpusScope({ directory: sourceDirectory, preparation: index });
    await validateCorpusScope({
      directory: path.dirname(options.preparationFile),
      preparation: index,
    });
  }
  const results = await Promise.all(
    [0, 1, 2].map(async (index) => {
      const directory = path.join(sourceDirectory, "learning", String(index));
      const result = learningEvidenceSchema.parse(
        await readFrozenArtifact(path.join(directory, "result.json")),
      );
      const ledger = await readInvocationLedger(directory);
      if (
        result.preparation !== index ||
        !result.completed ||
        result.calls.length === 0 ||
        result.calls.length !== ledger.calls ||
        ledger.pending ||
        result.calls.length > preparation.learner.maximumCalls ||
        result.calls.some(
          (call) =>
            call.isError ||
            call.model !== preparation.learner.model ||
            call.cliVersion !== preparation.learner.cliVersion,
        )
      )
        throw new Error("Retained preparation is incomplete or exceeds its pinned scope.");
      return result;
    }),
  );
  const environments = await captureSets(sourceDirectory);
  for (const engine of ["codex", "claude-code"] as const)
    for (const repository of ["atlas", "boreal"] as const) {
      const before = original.environments[engine][repository];
      const after = environments[engine][repository];
      if (
        fingerprint([before.skills, before.routing, before.told]) !==
        fingerprint([after.skills, after.routing, after.told])
      )
        throw new Error("Starting guidance changed during retained learning.");
      for (const candidate of after.deep)
        requireManualPreserved({
          original: before.skills,
          candidate,
          allowPublishedAdditions: true,
        });
    }
  const directory = path.dirname(options.preparationFile);
  const environmentsFile = path.join(directory, "environments.json");
  if (await Bun.file(environmentsFile).exists())
    throw new Error("Prepared environments already exist; preserve the previous result.");
  const prepared = preparedSchema.parse({
    preparation,
    preparationFingerprint: fingerprint(preparation),
    learning: results,
    environments,
    origin: {
      preparationFingerprint: source.preparationFingerprint,
      product: source.product,
      sourceFingerprint: source.fingerprint,
      resultFingerprints: results.map((result) => fingerprint(result)),
      reusedCalls: results.reduce((total, result) => total + result.calls.length, 0),
      reason:
        "Learning implementation, fixture setup, synthetic corpus, runtime, learner, and initial guidance match the sealed source. Actual outputs are reused without modification or additional calls.",
    },
  });
  await writeFrozenArtifact({ file: environmentsFile, value: prepared });
  const assessmentTemplate = path.join(directory, "learning-assessment-draft.json");
  await writeFrozenArtifact({
    file: assessmentTemplate,
    value: {
      preparationFingerprint: prepared.preparationFingerprint,
      decision: "draft",
      preparations: results.map((entry) => ({
        preparation: entry.preparation,
        publishedFingerprint: fingerprint(entry.published),
        missing: entry.missing,
        unsupported: entry.unsupported,
        justification:
          "Review retained published text and negative evidence before marking reviewed.",
      })),
    },
  });
  return {
    environmentsFile,
    assessmentTemplate,
    completed: true,
    reusedCalls: prepared.origin?.reusedCalls,
    origin: prepared.origin,
  };
}
