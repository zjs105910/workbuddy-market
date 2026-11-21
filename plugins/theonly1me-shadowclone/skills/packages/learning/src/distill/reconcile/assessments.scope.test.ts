import { origin, storedRule, contextWithRule } from "./assessments.fixtures";
import { expect, test } from "bun:test";
import { explicitProfileEvidence, profileEvidenceId } from "@shadowclone/profile";
import { applyReconciliation } from "./apply";

test("explicit global guidance promotes an existing mined repository rule", () => {
  const applied = applyReconciliation({
    context: contextWithRule(storedRule()),
    output: {
      existingRules: [
        {
          ruleToken: "rule-1",
          verdict: "reinforces",
          observed: "The user stated a personal preference.",
          evidenceTokens: ["evidence-1"],
          proposedTitle: "",
          proposedBody: "",
          axisChoiceToken: "",
        },
      ],
      newRules: [],
      assessments: [
        {
          evidenceToken: ["evidence", "1"].join("-"),
          intent: "preference",
          durable: true,
          explicit: true,
          scope: "global",
        },
      ],
    },
  });

  expect(applied.rules[0]?.scope).toBe("global");
  expect(applied.rules[0]?.originDirectory).toBeNull();
  expect(applied.rules[0]?.repositoryName).toBeNull();
});

test("a global assessment relocates matching stored evidence without a duplicate rule", () => {
  const evidence = explicitProfileEvidence(
    profileEvidenceId({
      originId: origin.id,
      sessionId: "session-1",
      timestamp: 1,
      kind: "user-steering",
      category: "user-episode",
    }),
  );

  const applied = applyReconciliation({
    context: contextWithRule(storedRule([evidence])),
    output: {
      existingRules: [],
      newRules: [],
      assessments: [
        {
          evidenceToken: ["evidence", "1"].join("-"),
          intent: "preference",
          durable: true,
          explicit: true,
          scope: "global",
        },
      ],
    },
  });

  expect(applied.rules[0]?.scope).toBe("global");
  expect(applied.changes[0]?.kind).toBe("scope");
});
