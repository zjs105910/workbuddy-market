import { expect, test } from "bun:test";
import { contextWithRule, storedRule } from "./assessments.fixtures";
import { applyReconciliation } from "./apply";
import { repositoryBound } from "./scope";

test("repository-bound wording and paths are detected without flagging personal phrasing", () => {
  expect(repositoryBound("Never read services/billing/src/fixtures/ in this repository.")).toBe(true);
  expect(repositoryBound("Run the checks in src/index.ts before committing.")).toBe(true);
  expect(repositoryBound("Keep the codebase free of generated files in this repo.")).toBe(true);
  expect(repositoryBound("Write commit messages as a subject line only, and/or ask before pushing.")).toBe(false);
  expect(repositoryBound("Read ~/.agents/skills/clean-code/SKILL.md and https://example.com/docs/guide first.")).toBe(false);
});

test("global evidence does not promote a repository-bound rule", () => {
  const evidenceToken = ["evidence", "1"].join("-");
  const rule = { ...storedRule(), body: "Never modify services/billing/src/fixtures/ in this repository." };
  const applied = applyReconciliation({
    context: contextWithRule(rule),
    output: {
      existingRules: [{
        ruleToken: "rule-1", verdict: "reinforces", observed: "The user restated the instruction.",
        evidenceTokens: [evidenceToken], proposedTitle: "", proposedBody: "", axisChoiceToken: "",
      }],
      newRules: [],
      assessments: [{ evidenceToken, intent: "preference", durable: true, explicit: true, scope: "global" }],
    },
  });

  expect(applied.rules[0]?.scope).toBe("project");
  expect(applied.rules[0]?.repositoryName).toBe("current");
});
