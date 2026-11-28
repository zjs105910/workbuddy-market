import { mkdir, readdir } from "node:fs/promises";
import path from "node:path";
import { authorizeFixedRun } from "../index";
import { requirePrivateDirectory, treeFingerprint } from "../../native/files";
import { fingerprint } from "../../shared/structured";
import { fixedCliVersion, fixedRuntime } from "../identity";
import { readFrozenArtifact, writeFrozenArtifact } from "../workflow/preparation";
import { benchmarkFingerprint, developmentCases, repositoryInstructions } from "./definition";
import { readLearnedEnvironments } from "./learning";
import { readPreparation, requireProduct } from "./preparation";
import { publishedHeldout, readHeldout } from "./seal";
import { frozenSchema, scopeSchema, type FrozenSuite } from "./schema";
import { graderFingerprint } from "./identity";
import { routingCases } from "./routing";

export function invocationCeiling(options: {
  cases: FrozenSuite["cases"];
  experiment: FrozenSuite["experiment"];
  preparationCalls: number;
  phase?: FrozenSuite["phase"];
}) {
  const setups = options.experiment === "learning" && options.phase !== "preflight" ? 5 : 2;
  const candidateCalls =
    options.cases.reduce((total, entry) => total + entry.task.turns.length, 0) *
    setups *
    (options.phase === "preflight" ? 1 : 3);
  const retryCalls = candidateCalls;
  return {
    preparationCalls: options.preparationCalls,
    candidateCalls,
    retryCalls,
    maximumCalls: candidateCalls + retryCalls,
    completeExperimentCeiling: options.preparationCalls + candidateCalls + retryCalls,
  };
}

export async function prepareReusableSuite(options: {
  preparationFile: string;
  environmentsFile?: string;
  directory: string;
  experiment: FrozenSuite["experiment"];
  phase: FrozenSuite["phase"];
  engine: FrozenSuite["host"]["engine"];
  model: string;
  effort: FrozenSuite["host"]["effort"];
  cliVersion?: string;
}) {
  const preparation = await readPreparation(options.preparationFile);
  await requireProduct(preparation.product);
  const learned = options.environmentsFile
    ? await readLearnedEnvironments(options.environmentsFile)
    : null;
  if (options.experiment === "learning" && options.phase !== "preflight" && !learned)
    throw new Error("Learning experiment requires three actual preparation receipts.");
  if (
    options.experiment === "learning" &&
    options.phase === "qualification" &&
    learned?.learning.some((entry) => entry.inspection !== "reviewed")
  )
    throw new Error(
      "Qualification requires a recorded semantic assessment of all three actual preparation outputs; guidance is never corrected.",
    );
  if (learned && learned.preparationFingerprint !== fingerprint(preparation))
    throw new Error("Prepared guidance belongs to another cohort.");
  const directory = await requirePrivateDirectory(options.directory);
  await mkdir(directory, { recursive: true, mode: 0o700 });
  if ((await readdir(directory)).length > 0)
    throw new Error("Suite preparation requires an empty private directory.");
  const cases =
    options.experiment === "routing"
      ? routingCases.map((entry) => entry.case)
      : options.phase === "qualification"
        ? [...developmentCases, ...(await readHeldout(preparation.bundleFile)).cases]
        : developmentCases;
  const ceiling = invocationCeiling({
    cases,
    experiment: options.experiment,
    phase: options.phase,
    preparationCalls:
      options.experiment === "learning" && options.phase !== "preflight"
        ? preparation.maximumCalls
        : 0,
  });
  const templateDirectory = path.join(directory, "template");
  await mkdir(templateDirectory, { mode: 0o700 });
  await Bun.write(path.join(templateDirectory, "AGENTS.md"), repositoryInstructions);
  await Bun.write(path.join(templateDirectory, "CLAUDE.md"), "@AGENTS.md\n");
  await Bun.write(
    path.join(templateDirectory, "package.json"),
    JSON.stringify({
      name: "synthetic-evaluation-workspace",
      private: true,
      scripts: { test: "bun test" },
    }),
  );
  const frozen = frozenSchema.parse({
    protocol: "preference-respect-v3",
    version: 3,
    id: crypto.randomUUID(),
    experiment: options.experiment,
    phase: options.phase,
    benchmarkFingerprint,
    graderFingerprint: await graderFingerprint(),
    reviewFingerprint: preparation.reviewFingerprint,
    bundleFingerprint: publishedHeldout.fingerprint,
    product: preparation.product,
    runtime: preparation.runtime,
    host: {
      engine: options.engine,
      model: options.model,
      effort: options.effort,
      cliVersion: options.cliVersion ?? (await fixedCliVersion(options.engine)),
    },
    learner: preparation.learner,
    templateDirectory,
    templateFingerprint: await treeFingerprint(templateDirectory),
    privateBundle: preparation.bundleFile,
    cases,
    environments: learned?.environments ?? preparation.environments,
    routingEnvironments: preparation.routingEnvironments,
    learning:
      options.experiment === "learning" && options.phase !== "preflight"
        ? (learned?.learning ?? [])
        : [],
    repetitions: options.phase === "preflight" ? 1 : 3,
    ...(learned?.origin ? { learningOrigin: learned.origin } : {}),
    limits: {
      preparationCalls: ceiling.preparationCalls,
      candidateCalls: ceiling.candidateCalls,
      retryCalls: ceiling.retryCalls,
      maximumCalls: ceiling.maximumCalls,
      codeSeconds: 240,
      adviceSeconds: 120,
    },
  });
  const suiteFile = path.join(directory, "suite.json");
  await writeFrozenArtifact({ file: suiteFile, value: frozen });
  return {
    suiteFile,
    fingerprint: fingerprint(frozen),
    invocationCeiling: ceiling,
    host: frozen.host,
    cases: cases.length,
    heldoutIncluded: options.phase === "qualification" && options.experiment === "learning",
  };
}

export async function readReusableSuite(file: string) {
  const suite = frozenSchema.parse(await readFrozenArtifact(file));
  if (
    suite.benchmarkFingerprint !== benchmarkFingerprint ||
    suite.graderFingerprint !== (await graderFingerprint())
  )
    throw new Error("Frozen benchmark or grader fingerprint is stale.");
  if (fingerprint(suite.runtime) !== fingerprint(fixedRuntime))
    throw new Error("Frozen runtime changed; requalify before execution.");
  if ((await treeFingerprint(suite.templateDirectory)) !== suite.templateFingerprint)
    throw new Error("Frozen workspace template changed.");
  if (suite.bundleFingerprint !== publishedHeldout.fingerprint)
    throw new Error("Held-out seal changed.");
  const expected =
    suite.experiment === "routing"
      ? routingCases.map((entry) => entry.case)
      : suite.phase !== "qualification"
        ? developmentCases
        : [...developmentCases, ...(await readHeldout(suite.privateBundle)).cases];
  if (fingerprint(expected) !== fingerprint(suite.cases))
    throw new Error("Case set differs from fixed suite.");
  const ceiling = invocationCeiling({
    cases: suite.cases,
    experiment: suite.experiment,
    phase: suite.phase,
    preparationCalls: suite.limits.preparationCalls,
  });
  if (suite.repetitions !== (suite.phase === "preflight" ? 1 : 3))
    throw new Error("Repetition/preparation assignment changed.");
  if (
    ceiling.candidateCalls !== suite.limits.candidateCalls ||
    ceiling.retryCalls !== suite.limits.retryCalls ||
    ceiling.maximumCalls !== suite.limits.maximumCalls
  )
    throw new Error("Invocation ceiling changed.");
  for (const host of Object.values(suite.environments))
    for (const repository of Object.values(host)) {
      for (const environment of [
        repository.skills,
        repository.routing,
        repository.told,
        ...repository.deep,
      ])
        if (environment.fingerprint !== fingerprint(environment.files))
          throw new Error("Guidance fingerprint changed.");
    }
  for (const host of Object.values(suite.routingEnvironments))
    for (const environment of Object.values(host))
      if (environment.fingerprint !== fingerprint(environment.files))
        throw new Error("Routing guidance fingerprint changed.");
  return suite;
}

export async function authorizeReusableRun(options: { suiteFile: string; fingerprint: string }) {
  const suite = await readReusableSuite(options.suiteFile);
  if (fingerprint(suite) !== options.fingerprint)
    throw new Error("Run approval must match this suite fingerprint.");
  await authorizeFixedRun({ engine: suite.host.engine });
  const scope = scopeSchema.parse({
    suiteFingerprint: options.fingerprint,
    host: suite.host,
    phase: suite.phase,
    experiment: suite.experiment,
    maximumCalls: suite.limits.maximumCalls,
    decision: "approved",
  });
  const scopeFile = path.join(path.dirname(options.suiteFile), "run-scope.json");
  await writeFrozenArtifact({ file: scopeFile, value: scope });
  return { scopeFile, invocationCeiling: scope.maximumCalls, host: scope.host, phase: scope.phase };
}
