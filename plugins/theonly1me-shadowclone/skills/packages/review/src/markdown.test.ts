import { expect, test } from "bun:test";
import { reviewMarkdown } from "./markdown";
import type { ReviewResult } from "./types";

const headSha = "0123456789abcdef0123456789abcdef01234567";

const result: ReviewResult = {
  version: 1,
  pull: { repository: "example/project", number: 7, title: "t", body: "", baseRefName: "main", baseSha: "a".repeat(40), headSha },
  model: "claude-opus-5-5",
  findings: [
    {
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
      suggestion: null,
      refutation: "No other path applies the discount.",
      candidates: [],
    },
  ],
  commentableLines: {},
  skippedPaths: [],
  toolchain: [],
  dropped: [{ title: "Cache never expires", path: "src/cache.ts", line: 4, reason: "the quoted code is not at `src/cache.ts:4`" }],
  candidates: { dropped: [{ id: "S1", title: "js-eval: Code built from a string at runtime", path: "src/a.ts", line: 3, reason: "The string is a constant." }], undecided: [] },
  rejections: [],
  statistics: { modelFindings: 2, droppedForEvidence: 1, correctionRound: "none", certainRuleHits: 0, signalRuleHits: 0, durationMilliseconds: 40_000, costUsd: null },
};

test("evidence links in the local review keep the full head commit", () => {
  expect(reviewMarkdown(result)).toContain(`https://github.com/example/project/blob/${headSha}/src/order.ts#L12`);
});

test("the local review lists each finding that failed the evidence check, with its reason", () => {
  expect(reviewMarkdown(result)).toContain("- Cache never expires (`src/cache.ts:4`): the quoted code is not at `src/cache.ts:4`");
});

test("the local review lists each signal that the reviewer checked and dropped, with its reason", () => {
  expect(reviewMarkdown(result)).toContain("- S1 js-eval: Code built from a string at runtime (`src/a.ts:3`): The string is a constant.");
});

test("a branch review names the head commit and shows plain locations, because the commit may not be on GitHub", () => {
  const markdown = reviewMarkdown({ ...result, pull: { ...result.pull, repository: "local/project", number: null } });

  expect(markdown).toStartWith(`# Review of local/project at ${headSha.slice(0, 7)}`);
  expect(markdown).toContain("- `src/order.ts:12`: `return subtotal;`");
  expect(markdown).not.toContain("https://github.com");
});
