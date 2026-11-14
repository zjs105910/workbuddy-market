import { expect, test } from "bun:test";
import type { Finding, ReviewResult } from "../types";
import { reviewMarker, reviewPayload } from "./payload";

function finding(overrides: Partial<Finding>): Finding {
  return {
    path: "src/order.ts",
    line: 12,
    severity: "high",
    category: "correctness",
    source: "investigation",
    title: "Total ignores discounts",
    explanation: "The new total skips the discount step.",
    failureScenario: "An order with a 10% discount is charged the full price.",
    evidence: [{ source: "code", location: "src/order.ts:12", quote: "return subtotal;" }],
    rule: null,
    suggestion: null,
    refutation: "The refuter found no other discount path.",
    candidates: [],
    ...overrides,
  };
}

function result(findings: readonly Finding[]): ReviewResult {
  return {
    version: 1,
    pull: { repository: "example/project", number: 7, title: "t", body: "", baseRefName: "main", baseSha: "a".repeat(40), headSha: "b".repeat(40) },
    model: "claude-opus-5-5",
    findings: [...findings],
    commentableLines: { "src/order.ts": [[10, 14]] },
    skippedPaths: [],
    toolchain: [],
    dropped: [],
    candidates: { dropped: [], undecided: [] },
    rejections: [],
    statistics: { modelFindings: findings.length, droppedForEvidence: 0, correctionRound: "none", certainRuleHits: 0, signalRuleHits: 0, durationMilliseconds: 1000, costUsd: null },
  };
}

test("a finding inside a diff hunk is inline and one outside goes to the review body", () => {
  const payload = reviewPayload(result([finding({}), finding({ path: "src/caller.ts", line: 30, title: "Caller passes the old shape" })]));

  expect(payload.comments.map((comment) => [comment.path, comment.line, comment.side])).toEqual([["src/order.ts", 12, "RIGHT"]]);
  expect(payload.body).toContain("`src/caller.ts:30`");
  expect(payload.event).toBe("COMMENT");
});

test("mentions, cross-repository references, and issue links cannot notify anyone", () => {
  const payload = reviewPayload(
    result([finding({ explanation: "@octocat broke this in other/project#12, see https://github.com/other/project/pull/12" })]),
  );
  const [comment] = payload.comments;

  expect(comment?.body).toContain("`@octocat`");
  expect(comment?.body).toContain("`other/project#12`");
  expect(comment?.body).toContain("`https://github.com/other/project/pull/12`");
});

test("a credential quoted by the model is redacted before posting", () => {
  const token = ["ghp", "R8kLm2Qw9ZxT4vB7nC1dF6gH3jK5pS0uYeA2"].join("_");
  const payload = reviewPayload(result([finding({ explanation: `The fixture embeds ${token}.` })]));

  expect(JSON.stringify(payload)).not.toContain(token);
});

test("a review with no findings still says what it reviewed", () => {
  const payload = reviewPayload(result([]));

  expect(payload.body).toStartWith("Shadowclone reviewed bbbbbbb and found no defect that it could confirm.");
  expect(payload.body).toEndWith(reviewMarker);
});

test("code evidence links to the exact line at the reviewed head", () => {
  const payload = reviewPayload(result([finding({})]));
  const [comment] = payload.comments;

  expect(comment?.body).toContain(`[\`src/order.ts:12\`](https://github.com/example/project/blob/${"b".repeat(40)}/src/order.ts#L12): \`return subtotal;\``);
});

test("a documentation link to a GitHub issue is not a clickable cross-reference", () => {
  const payload = reviewPayload(
    result([
      finding({
        evidence: [
          { source: "code", location: "src/order.ts:12", quote: "return subtotal;" },
          { source: "doc", location: "https://github.com/other/library/issues/9", quote: "the cache is not cleared" },
        ],
      }),
    ]),
  );

  expect(payload.comments[0]?.body).toContain("- `https://github.com/other/library/issues/9`: \"the cache is not cleared\"");
});
