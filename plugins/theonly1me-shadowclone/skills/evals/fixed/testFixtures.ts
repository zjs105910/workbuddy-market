import { studyFixture } from "../native/study/fixtures";
import type { MatrixReceipt } from "../native/study/matrix";
import type { FixedSuite } from "./freeze";
import { benchmarkFingerprint, fixedDefinition, internalArms } from "./definition";
import { referenceRecord } from "./calibration";
import { fingerprint } from "../shared/structured";
import { fixedRuntime } from "./identity";

export async function fixedFixture() {
  const fixture = await studyFixture({ tasks: fixedDefinition.tasks });
  const frozen: FixedSuite = { protocol: "preference-respect-v1", version: 1, benchmark: "engineering-preferences-v1",
    benchmarkFingerprint, graderFingerprint: "a".repeat(64), runtime: fixedRuntime, branch: "synthetic", suite: { ...fixture.suite, keyItems: fixedDefinition.profile } };
  const receipt: MatrixReceipt = { protocol: "preference-study-v1", phase: "scored", suiteFingerprint: fingerprint(frozen.suite),
    deadlineAt: Date.now() + 60_000, status: "complete", failure: null,
    runs: frozen.suite.tasks.flatMap((task) => internalArms.map((arm) => ({ ...referenceRecord(task), arm,
      productCommit: frozen.suite.productCommit, productTreeFingerprint: frozen.suite.productTreeFingerprint }))) };
  return { ...fixture, frozen, receipt };
}
