import { mkdir } from "node:fs/promises";
import path from "node:path";
import { z } from "zod";
import { learn } from "@shadowclone/cli";
import { readConfig, writeConfig, readManagedPolicy, projectPaths } from "@shadowclone/core";
import type { NativeEngineRunner } from "@shadowclone/agents";
import { evaluationBudget } from "../../shared/accounting";
import { lockEvaluation } from "../../shared/lock";
import { fingerprint } from "../../shared/structured";
import { treeFingerprint } from "../../native/files";
import { workflowLearningRunner } from "../workflow/learner";
import { readFrozenArtifact, writeFrozenArtifact } from "../workflow/preparation";
import { reusableLayout, requireManualPreserved } from "./environments";
import {
  captureSets,
  readPreparation,
  requireProduct,
  preparationSchema,
  preparationScopeSchema,
} from "./preparation";
import { learningEvidenceSchema, learningOriginSchema, type FrozenSuite } from "./schema";
import { inspectPreparation } from "./preparationEvidence";
import type { LearningCall } from "../workflow/schema";
import { readAssessment } from "./assessment";
import { validateCorpusScope } from "./corpusScope";
import { preparationLearningLimits } from "./learningLimits";

export const preparedSchema = z.strictObject({
  preparation: preparationSchema,
  preparationFingerprint: z.string(),
  learning: z.array(learningEvidenceSchema).length(3),
  environments: preparationSchema.shape.environments,
  origin: learningOriginSchema.optional(),
});

export async function learnReusableEnvironments(options: {
  preparationFile: string;
  scopeFile: string;
  runner?: NativeEngineRunner;
  managedConfigPath?: string | null;
}) {
  const preparation = await readPreparation(options.preparationFile);
  const scope = preparationScopeSchema.parse(await readFrozenArtifact(options.scopeFile));
  if (
    scope.preparationFingerprint !== fingerprint(preparation) ||
    fingerprint(scope.learner) !== fingerprint(preparation.learner) ||
    scope.maximumCalls !== preparation.maximumCalls
  )
    throw new Error("Newly approved learning scope does not match this preparation.");
  const managedConfigPath =
    options.managedConfigPath === undefined
      ? projectPaths.managedConfigFile
      : options.managedConfigPath;
  const policy = await readManagedPolicy(managedConfigPath);
  if (
    !policy.enabled ||
    policy.distillation !== "allowed" ||
    !policy.allowedEngines.includes("codex") ||
    !policy.allowedSources.includes("claude-code") ||
    !policy.allowedSources.includes("skill-library")
  )
    throw new Error("Managed policy prohibits synthetic learning.");
  await requireProduct(preparation.product);
  console.log(
    `Pinned Codex learning ceiling: ${preparation.maximumCalls} calls across three independent preparations.`,
  );
  const directory = path.dirname(options.preparationFile);
  const release = await lockEvaluation(directory);
  const layout = reusableLayout(directory);
  const evidence: FrozenSuite["learning"] = [];
  const incomplete = (file: string) => ({
    environmentsFile: null,
    assessmentTemplate: null,
    learning: evidence,
    completed: false,
    calls: evidence.reduce((total, entry) => total + entry.calls.length, 0),
    incompletePreparationFile: file,
  });
  try {
    for (const preparation of [0, 1, 2]) await validateCorpusScope({ directory, preparation });
    for (const index of [0, 1, 2]) {
      const learningDirectory = path.join(directory, "learning", String(index));
      const resultFile = path.join(learningDirectory, "result.json");
      if (await Bun.file(resultFile).exists()) {
        const retained = learningEvidenceSchema.parse(await readFrozenArtifact(resultFile));
        evidence.push(retained);
        if (!retained.completed) return incomplete(resultFile);
        continue;
      }
      const paths = layout.paths(`deep-${index}`);
      const input = preparation.inputs[index];
      if (!input || (await treeFingerprint(paths.claudeProjectsDirectory)) !== input.corpus)
        throw new Error("Frozen correction input changed.");
      const budgetFile = path.join(learningDirectory, "budget.json");
      if (await Bun.file(budgetFile).exists())
        throw new Error(
          "Interrupted preparation retained. It cannot silently restart; preserve its calls and prepare a newly authorized cohort.",
        );
      if ((await treeFingerprint(paths.shadowcloneDirectory)) !== input.state)
        throw new Error("Frozen learning state changed.");
      await mkdir(learningDirectory, { recursive: true, mode: 0o700 });
      const budget = await evaluationBudget({
        directory: learningDirectory,
        resume: false,
        maximumCalls: preparation.learner.maximumCalls,
      });
      const calls: LearningCall[] = [];
      const config = await readConfig({ configPath: paths.configFile });
      await writeConfig({
        configPath: paths.configFile,
        config: {
          ...config,
          sources: { ...config.sources, "claude-code": true },
          distillation: { deep: true, automatic: false },
        },
      });
      let completed = true;
      try {
        await learn({
          paths,
          workingDirectory: layout.workspace({ arm: `deep-${index}`, repository: "atlas" }),
          managedConfigPath,
          deep: true,
          apply: true,
          confirm: () => true,
          engine: "codex",
          model: preparation.learner.model,
          reasoningEffort: preparation.learner.effort,
          maximumCalls: preparation.learner.maximumCalls,
          limits: preparationLearningLimits(preparation.learner),
          writeLine: () => {},
          runner: workflowLearningRunner({
            directory: learningDirectory,
            budget,
            configuration: preparation.learner,
            calls,
            runner: options.runner,
            blockedPaths: [directory, path.dirname(preparation.bundleFile), process.cwd()],
          }),
        });
      } catch (error) {
        completed = false;
        await writeFrozenArtifact({
          file: path.join(learningDirectory, "diagnostic.json"),
          value: {
            stage: "learning",
            message: error instanceof Error ? error.message : String(error),
          },
        });
      }
      completed = completed && calls.length > 0 && calls.every((call) => !call.isError);
      const result = await inspectPreparation({ directory, preparation: index, calls, completed });
      evidence.push(result);
      await writeFrozenArtifact({ file: resultFile, value: result });
      if (!completed) return incomplete(resultFile);
    }
    const environments = await captureSets(directory);
    for (const engine of ["codex", "claude-code"] as const)
      for (const repository of ["atlas", "boreal"] as const) {
        const before = preparation.environments[engine]?.[repository];
        const after = environments[engine]?.[repository];
        if (
          !before ||
          !after ||
          fingerprint([before.skills, before.routing, before.told]) !==
            fingerprint([after.skills, after.routing, after.told])
        )
          throw new Error("Starting environments changed during learning.");
        for (const deep of after.deep)
          requireManualPreserved({
            original: before.skills,
            candidate: deep,
            allowPublishedAdditions: true,
          });
      }
    await requireProduct(preparation.product);
    const prepared = preparedSchema.parse({
      preparation,
      preparationFingerprint: fingerprint(preparation),
      learning: evidence,
      environments,
    });
    const environmentsFile = path.join(directory, "environments.json");
    await writeFrozenArtifact({ file: environmentsFile, value: prepared });
    const assessmentTemplate = path.join(directory, "learning-assessment-draft.json");
    await writeFrozenArtifact({
      file: assessmentTemplate,
      value: {
        preparationFingerprint: prepared.preparationFingerprint,
        decision: "draft",
        preparations: evidence.map((entry) => ({
          preparation: entry.preparation,
          publishedFingerprint: fingerprint(entry.published),
          missing: entry.missing,
          unsupported: entry.unsupported,
          justification:
            "Inspect actual published text, conditions, scope, supersession, and negative evidence before marking reviewed.",
        })),
      },
    });
    return {
      environmentsFile,
      assessmentTemplate,
      learning: evidence,
      completed: evidence.every((entry) => entry.completed),
      calls: evidence.reduce((total, entry) => total + entry.calls.length, 0),
    };
  } finally {
    await release();
  }
}

export async function readLearnedEnvironments(file: string) {
  const prepared = preparedSchema.parse(await readFrozenArtifact(file));
  const original = await readPreparation(path.join(path.dirname(file), "preparation.json"));
  if (
    prepared.preparationFingerprint !== fingerprint(original) ||
    fingerprint(prepared.preparation) !== fingerprint(original)
  )
    throw new Error("Preparation provenance differs.");
  for (const entry of prepared.learning)
    if (
      entry.calls.length > original.learner.maximumCalls ||
      entry.calls.some(
        (call) =>
          call.model !== original.learner.model ||
          call.cliVersion !== original.learner.cliVersion ||
          call.isError,
      )
    )
      throw new Error("Learning calls exceed scope or have unconfirmed identities.");
  if (new Set(prepared.learning.map((entry) => entry.preparation)).size !== 3)
    throw new Error("Three independent preparations required.");
  return {
    ...prepared,
    learning: await readAssessment({
      environmentsFile: file,
      evidence: prepared.learning,
      preparationFingerprint: prepared.preparationFingerprint,
    }),
  };
}
