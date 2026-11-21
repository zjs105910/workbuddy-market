import { studySuiteSchema } from "../../native/study/schema";
import { fingerprint } from "../../shared/structured";
import { expectedGuidance } from "./oracle";
import type { FrozenSuite, PreferenceCase, Setup } from "./schema";

export const nativeSetups = {
  bare: "bare",
  skills: "original",
  routing: "first-time",
  told: "told",
  deep: "deep",
} as const;
export function selectedEnvironment(options: {
  suite: FrozenSuite;
  setup: Setup;
  case: PreferenceCase;
  repetition: number;
}) {
  if (options.setup === "bare") return undefined;
  if (options.suite.experiment === "routing") {
    if (options.setup !== "skills" && options.setup !== "routing")
      throw new Error("Routing experiment has only skills and routing setups.");
    return options.suite.routingEnvironments[options.suite.host.engine][options.setup];
  }
  const environments =
    options.suite.environments[options.suite.host.engine][options.case.repository];
  const environment =
    options.setup === "deep" ? environments.deep[options.repetition] : environments[options.setup];
  if (!environment) throw new Error("Missing guidance for this preparation group.");
  return environment;
}

export function nativeSuite(options: { suite: FrozenSuite; cases: readonly PreferenceCase[] }) {
  const empty = { files: [], fingerprint: fingerprint([]) };
  return studySuiteSchema.parse({
    protocol: "preference-study-v1",
    version: 1,
    studyId: options.suite.id,
    productCommit: options.suite.product.commit,
    productTreeFingerprint: options.suite.product.tree,
    templateDirectory: options.suite.templateDirectory,
    templateFingerprint: options.suite.templateFingerprint,
    cliVersion: options.suite.host.cliVersion,
    engine: options.suite.host.engine,
    model: options.suite.host.model,
    effort: options.suite.host.effort,
    keyItems: expectedGuidance.map((rule) => ({
      id: rule.id,
      statement: rule.statement,
      group: "learned",
      evidence: "Independent synthetic oracle; never supplied in candidate prompts.",
    })),
    wizardBuild: ["synthetic"],
    resolutionRule:
      "Retain all actually published, missing, pending, and unsupported guidance without silent corrections.",
    arms: { original: empty, "first-time": empty, deep: empty },
    memory: [],
    tasks: options.cases.map((entry) => entry.task),
    droppedChecks: [],
    analysis: {
      repetitions: options.suite.repetitions,
      bootstrapSeed: 20261002,
      bootstrapSamples: 10000,
    },
    limits: {
      maximumCalls: Math.min(1000, options.suite.limits.maximumCalls),
      concurrency: 1,
      codeTurnSeconds: 240,
      adviceTurnSeconds: 120,
      judgeSeconds: 30,
    },
  });
}
