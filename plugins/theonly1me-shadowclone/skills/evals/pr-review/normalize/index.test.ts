import { expect, test } from "bun:test";
import { localShadowcloneFindings, shadowcloneFindings } from "./index";

test("findings in the review body and inline comments are both counted", () => {
  const raw = {
    reviews: [{ id: 7, body: "Summary.\n\n`src/a.ts:12`\n\n**high correctness: Wrong total**\n\nThe total is wrong.\n\n<!-- shadowclone-review -->", submitted_at: "2026-10-09T10:00:00Z", user: { login: "clone[bot]" } }],
    reviewComments: [{ pull_request_review_id: 7, path: "src/b.ts", line: 3, body: "**medium security: Unsafe call**", user: { login: "clone[bot]" } }],
    issueComments: [],
  };

  expect(shadowcloneFindings({ caseId: "c01", raw, startedAt: "2026-10-09T09:00:00Z" }).map((finding) => [finding.path, finding.line])).toEqual([
    ["src/b.ts", 3],
    ["src/a.ts", 12],
  ]);
});

test("a local review counts the findings in its result, under the arm that ran it", () => {
  const finding = {
    path: "src/order.ts",
    line: 12,
    severity: "high",
    category: "correctness",
    source: "investigation",
    title: "Total skips the discount",
    explanation: "The total ignores the discount.",
    failureScenario: "A 10% coupon charges the full price.",
    evidence: [{ source: "code", location: "src/order.ts:12", quote: "return subtotal;" }],
    rule: null,
    suggestion: "Subtract the discount.",
    refutation: "No other path applies it.",
    candidates: [],
  };
  const raw = {
    version: 1,
    pull: { repository: "local/vite", number: null, title: "t", body: "", baseRefName: "main", baseSha: "a".repeat(40), headSha: "b".repeat(40) },
    model: "claude-opus-5-5",
    findings: [finding],
    commentableLines: {},
    skippedPaths: [],
    toolchain: [],
    dropped: [],
    candidates: { dropped: [], undecided: [] },
    rejections: [],
    statistics: { modelFindings: 1, droppedForEvidence: 0, correctionRound: "none", certainRuleHits: 0, signalRuleHits: 0, durationMilliseconds: 1, costUsd: null },
  };

  expect(localShadowcloneFindings({ arm: "shadowclone-branch", caseId: "c01", raw })).toEqual([
    {
      arm: "shadowclone-branch",
      caseId: "c01",
      path: "src/order.ts",
      line: 12,
      text: "Total skips the discount The total ignores the discount. A 10% coupon charges the full price. Subtract the discount.",
    },
  ]);
});
