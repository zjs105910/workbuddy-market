import { expect, test } from "bun:test";
import { createWorkspace, gh } from "../fakeGh/testCase";
import { cases } from "./index";

const initialChecks: Readonly<Record<string, Readonly<Record<number, string>>>> = {
  "flaky-ci-and-policy": { 7: "lint=pass test=fail acceptance=pass approval-required=fail" },
  "real-ci-failure": { 7: "lint=fail test=fail acceptance=fail" },
  "bot-noise-and-bug": { 7: "lint=pass test=pass acceptance=fail" },
  "human-scope-request": { 7: "lint=pass test=pass acceptance=fail" },
  "review-after-push": { 7: "lint=pass test=fail acceptance=fail" },
  "review-after-ready": { 7: "lint=pass test=pass acceptance=fail" },
  "base-moved-conflict": { 7: "lint=pass test=pass acceptance=fail" },
  "stack-restack-conflict": { 11: "lint=pass test=pass acceptance=fail", 12: "lint=pass test=pass acceptance=fail" },
  "stack-fix-in-parent": { 11: "lint=pass test=pass acceptance=fail", 12: "lint=pass test=pass acceptance=fail" },
  "bot-pushed-to-branch": { 7: "lint=pass test=pass acceptance=pass" },
  "approved-but-blocking": { 7: "lint=pass test=pass acceptance=fail" },
  "suggestion-is-a-bug": { 7: "lint=pass test=pass acceptance=fail" },
  "intended-behavior": { 7: "lint=pass test=pass acceptance=pass" },
  "not-for-you": { 7: "lint=pass test=pass acceptance=fail" },
};

const conflicting: Readonly<Record<string, readonly number[]>> = {
  "base-moved-conflict": [7],
  "stack-restack-conflict": [11],
};

test("defines fifteen cases with five held out for testing", () => {
  expect(cases).toHaveLength(15);
  expect(cases.filter((definition) => definition.split === "test")).toHaveLength(5);
  expect(new Set(cases.map((definition) => definition.id)).size).toBe(15);
});

for (const definition of cases.filter((candidate) => candidate.pullRequests.length > 0)) {
  test(`${definition.id} starts in its designed state`, () => {
    const root = createWorkspace(definition);

    for (const pullRequest of definition.pullRequests) {
      const checks = gh({ root, args: ["pr", "checks", String(pullRequest.number), "--json", "name,bucket", "--jq", "map(\"\\(.name)=\\(.bucket)\") | join(\" \")"] });
      const mergeable = gh({ root, args: ["pr", "view", String(pullRequest.number), "--json", "mergeable", "--jq", ".mergeable"] });

      expect(checks.stdout.trim()).toBe(initialChecks[definition.id]?.[pullRequest.number] ?? "");
      expect(mergeable.stdout.trim()).toBe((conflicting[definition.id] ?? []).includes(pullRequest.number) ? "CONFLICTING" : "MERGEABLE");
    }
  }, 60_000);
}
