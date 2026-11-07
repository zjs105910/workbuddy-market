import { fingerprint } from "../../shared/structured";
import { referenceRecord } from "./examples";
import { developmentCases } from "./definition";
import {
  families,
  frozenSchema,
  type PreferenceCase,
  type FrozenSuite,
  type Receipt,
} from "./schema";
import { matrixCells } from "./attempts";
import { nativeSetups } from "./bridge";

export function fixtureCases(): PreferenceCase[] {
  return families.flatMap((family) => {
    const cases = developmentCases.filter((entry) => entry.family === family);
    const first = cases[0];
    if (!first) throw new Error("Missing synthetic family.");
    return [
      ...cases,
      {
        ...first,
        split: "held-out" as const,
        task: { ...first.task, id: `${family}-synthetic-heldout` },
      },
    ];
  });
}

export function fixtureSuite(
  options: { cases?: PreferenceCase[]; experiment?: FrozenSuite["experiment"] } = {},
): FrozenSuite {
  const empty = { files: [], fingerprint: fingerprint([]) };
  const environments = { skills: empty, routing: empty, told: empty, deep: [empty, empty, empty] };
  const host = { atlas: environments, boreal: environments };
  const routing = { skills: empty, routing: empty };
  const cases = options.cases ?? fixtureCases();
  const candidateCalls = cases.length * (options.experiment === "routing" ? 2 : 5) * 3;
  return frozenSchema.parse({
    protocol: "preference-respect-v3",
    version: 3,
    id: "00000000-0000-4000-8000-000000000003",
    experiment: options.experiment ?? "learning",
    phase: "qualification",
    benchmarkFingerprint: "0".repeat(64),
    graderFingerprint: "0".repeat(64),
    reviewFingerprint: "0".repeat(64),
    bundleFingerprint: "0".repeat(64),
    product: { commit: "a".repeat(40), tree: "0".repeat(64), branch: "fixture" },
    runtime: { bun: "fixture", typescript: "fixture" },
    host: { engine: "codex", model: "synthetic", effort: "medium", cliVersion: "synthetic-cli" },
    learner: {
      engine: "codex",
      model: "synthetic",
      effort: "medium",
      cliVersion: "synthetic-cli",
      maximumCalls: 16,
      callSeconds: 120,
      deadlineSeconds: 1200,
    },
    templateDirectory: "/private/tmp/synthetic-template",
    templateFingerprint: "0".repeat(64),
    privateBundle: "/private/tmp/synthetic-heldout/bundle.json",
    cases,
    learning: [],
    environments: { codex: host, "claude-code": host },
    routingEnvironments: { codex: routing, "claude-code": routing },
    repetitions: 3,
    limits: {
      preparationCalls: 48,
      candidateCalls,
      retryCalls: candidateCalls,
      maximumCalls: candidateCalls * 2,
      codeSeconds: 240,
      adviceSeconds: 120,
    },
  });
}

export function fixtureReceipt(suite: FrozenSuite): Receipt {
  return {
    protocol: "preference-respect-v3",
    suiteFingerprint: fingerprint(suite),
    status: "complete",
    cells: matrixCells(suite).map((cell) => {
      const entry = suite.cases.find((entry) => entry.task.id === cell.caseId);
      if (!entry) throw new Error("Synthetic case missing.");
      const record = referenceRecord(entry);
      record.repeat = cell.repetition;
      record.arm = nativeSetups[cell.setup];
      record.productCommit = suite.product.commit;
      record.productTreeFingerprint = suite.product.tree;
      return {
        ...cell,
        attempts: [
          {
            number: 1,
            status: "complete",
            calls: 1,
            record,
            diagnostics: [],
            checks: [
              ...new Set([
                ...entry.task.checks.map((check) => check.id),
                ...entry.extraChecks.map((check) => check.id),
              ]),
            ].map((id) => ({
              id,
              keyItem: entry.family,
              verdict: "pass",
              evidence: "Synthetic pass.",
            })),
          },
        ],
      };
    }),
  };
}
