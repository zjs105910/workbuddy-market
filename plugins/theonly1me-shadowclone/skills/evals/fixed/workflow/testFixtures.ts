import { fixedFixture } from "../testFixtures";
import { workflowDefinition, workflowBenchmarkFingerprint, workflowInternalArms } from "./definition";
import { referenceRecord } from "../calibration";
import { fingerprint } from "../../shared/structured";
import type { WorkflowSuite } from "./freeze";
import type { MatrixReceipt } from "../../native/study/matrix";

export async function workflowFixture() {
  const fixture = await fixedFixture();
  const suite = { ...fixture.frozen.suite, keyItems: workflowDefinition.profile };
  const starting = { original: suite.arms.original, "first-time": suite.arms["first-time"] };
  const preparation = { protocol: "preference-respect-v2" as const, version: 2 as const, benchmarkFingerprint: workflowBenchmarkFingerprint,
    product: { commit: suite.productCommit, tree: suite.productTreeFingerprint, branch: "synthetic" },
    runtime: fixture.frozen.runtime, graderFingerprint: "a".repeat(64), corpusFingerprint: "c".repeat(64), learningStateFingerprint: "d".repeat(64),
    learner: { engine: "codex" as const, model: "synthetic-learner", effort: "medium" as const, cliVersion: "synthetic-cli",
      maximumCalls: 16, callSeconds: 120 as const, deadlineSeconds: 1200 as const },
    starting: { codex: starting, "claude-code": starting } };
  const frozen: WorkflowSuite = { protocol: "preference-respect-v2", version: 2, suite, environments: { protocol: "preference-respect-v2", preparation,
    preparationFingerprint: fingerprint(preparation), learning: { calls: [{ model: "synthetic-learner", cliVersion: "synthetic-cli", durationMs: 1, isError: false }],
      outcome: "complete", processedEpisodes: 2, pendingRules: 0, unresolvedSkills: 0, publishedRules: 2 },
    engines: { codex: suite.arms, "claude-code": suite.arms } } };
  const receipt: MatrixReceipt = { ...fixture.receipt, suiteFingerprint: fingerprint(suite), runs: suite.tasks.flatMap(task => workflowInternalArms.map(arm => {
    const run = referenceRecord(task);
    return { ...run, arm, turns: run.turns.map(turn => ({ ...turn, resolvedModel: suite.model })), productCommit: suite.productCommit, productTreeFingerprint: suite.productTreeFingerprint };
  })) };
  return { frozen, receipt, cleanup: fixture.cleanup };
}
