import { context, newRule, type Intent } from "./assessments.fixtures";
import { expect, test } from "bun:test";
import { applyReconciliation } from "./apply";

test.each(["additional-context", "cancellation", "unknown"] as const)(
  "%s cannot activate a preference even when the model proposes one",
  (intent: Intent) => {
    const output = {
      existingRules: [],
      newRules: [newRule],
      assessments: newRule.evidenceTokens.map((evidenceToken) => ({
        evidenceToken,
        intent,
        durable: true,
        scope: "repository" as const,
      })),
    };

    expect(applyReconciliation({ context, output }).rules).toEqual([]);
  },
);

test.each(["preference", "correction", "approval"] as const)(
  "durable %s supports a repository-scoped rule",
  (intent: Intent) => {
    const output = {
      existingRules: [],
      newRules: [newRule],
      assessments: newRule.evidenceTokens.map((evidenceToken) => ({
        evidenceToken,
        intent,
        durable: true,
        scope: "repository" as const,
      })),
    };

    const [rule] = applyReconciliation({ context, output }).rules;

    expect(rule?.status).toBe("active");
    expect(rule?.scope).toBe("project");
    expect(rule?.repositoryName).toBe("current");
  },
);

test("missing, temporary and duplicate assessments cannot add evidence", () => {
  for (const assessments of [
    undefined,
    newRule.evidenceTokens.map((evidenceToken) => ({
      evidenceToken,
      intent: "correction" as const,
      durable: false,
      scope: "repository" as const,
    })),
    [1, 2].map(() => ({
      evidenceToken: ["evidence", "1"].join("-"),
      intent: "preference" as const,
      durable: true,
      scope: "repository" as const,
    })),
  ]) {
    expect(
      applyReconciliation({
        context,
        output: { existingRules: [], newRules: [newRule], assessments },
      }).rules,
    ).toEqual([]);
  }
});

test("one explicit reusable instruction activates while one inference waits", () => {
  const singleRule = { ...newRule, evidenceTokens: ["evidence-1"] };

  const explicit = applyReconciliation({
    context,
    output: {
      existingRules: [],
      newRules: [singleRule],
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

  const inferred = applyReconciliation({
    context,
    output: {
      existingRules: [],
      newRules: [singleRule],
      assessments: [
        {
          evidenceToken: ["evidence", "1"].join("-"),
          intent: "preference",
          durable: true,
          explicit: false,
          scope: "global",
        },
      ],
    },
  });

  expect(explicit.rules[0]?.status).toBe("active");
  expect(explicit.rules[0]?.scope).toBe("global");
  expect(inferred.rules[0]?.status).toBe("candidate");
  expect(inferred.rules[0]?.scope).toBe("project");
});
