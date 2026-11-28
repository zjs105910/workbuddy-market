import { expect, test } from "bun:test";
import { learningRecord } from "@shadowclone/environment/testing";
import type { ReconciliationContext, ReconciliationOutput } from "./reconcile/types";
import { assessedCorrections } from "./feedback";

test("feedback requires a durable correction assessment linked to an existing rule", () => {
  const rule = learningRecord().rule;
  const signal = {
    kind: "user-steering" as const, category: "user-episode", label: "synthetic correction",
    sessionId: "codex:synthetic", timestamp: 2_000,
    origin: { id: "synthetic", directoryName: "synthetic", promotable: false },
    repositoryName: null, textRefs: [],
  };
  const context: ReconciliationContext = {
    batch: { origin: signal.origin, repositoryName: null, signals: [signal] },
    rules: [{ token: "rule-1", snapshot: { rule, promptTitle: rule.title, promptBody: rule.body,
      promptProposal: null, promptAppliesWhen: [] }, axisOptions: [] }], rejections: [],
    evidence: [{ token: "evidence-1", evidenceId: "opaque-evidence", signal }],
  };
  const output: ReconciliationOutput = {
    existingRules: [{ ruleToken: "rule-1", verdict: "reinforces", observed: "synthetic", evidenceTokens: ["evidence-1"],
      proposedTitle: "", proposedBody: "", axisChoiceToken: "" }], newRules: [],
    assessments: [{ evidenceToken: "evidence-1", intent: "correction", durable: true, scope: "global" }],
  };
  expect(assessedCorrections({ context, output })).toMatchObject([{ key: rule.key, evidenceId: "opaque-evidence" }]);
  for (const intent of ["approval", "unknown", "preference"] as const) {
    expect(assessedCorrections({ context, output: { ...output, assessments: [
      { evidenceToken: "evidence-1", intent, durable: true, scope: "global" },
    ] } })).toEqual([]);
  }
  expect(assessedCorrections({ context, output: { ...output, existingRules: [] } })).toEqual([]);
  expect(assessedCorrections({ context, output: { ...output, assessments: [
    { evidenceToken: "evidence-1", intent: "correction", durable: false, scope: "global" },
  ] } })).toEqual([]);
});
