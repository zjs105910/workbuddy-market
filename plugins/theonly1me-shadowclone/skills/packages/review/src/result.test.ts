import { expect, test } from "bun:test";
import { parseDiff } from "./collect/diff";
import type { ReviewPacket } from "./packet";
import { reviewResult } from "./result";
import type { RuleHit } from "./rules";
import type { Finding } from "./types";

const files = parseDiff(
  ["diff --git a/src/keys.ts b/src/keys.ts", "--- a/src/keys.ts", "+++ b/src/keys.ts", "@@ -1 +1,2 @@", " export const a = 1;", "+export const key = read();", ""].join("\n"),
);

function packet(ruleHits: readonly RuleHit[]): ReviewPacket {
  return {
    context: {
      facts: { repository: "example/project", number: 3, title: "t", body: "", baseRefName: "main", baseSha: "a".repeat(40), headSha: "b".repeat(40) },
      mergeBaseSha: "a".repeat(40),
      files,
      standards: { documents: [], omitted: [] },
      history: "",
    },
    ruleHits,
    toolchain: [],
  };
}

const certainHit: RuleHit = {
  ruleId: "credential-github-token",
  level: "certain",
  severity: "high",
  category: "security",
  title: "Credential committed",
  failure: "Anyone who can read the repository can use it.",
  path: "src/keys.ts",
  line: 2,
};

function modelFinding(line: number): Finding {
  return {
    path: "src/other.ts",
    line,
    severity: "low",
    category: "correctness",
    source: "investigation",
    title: `Finding ${line}`,
    explanation: "e",
    failureScenario: "f",
    evidence: [{ source: "code", location: `src/other.ts:${line}`, quote: "x" }],
    rule: null,
    suggestion: null,
    refutation: "r",
    candidates: [],
  };
}


function resultFor(options: { readonly hits: readonly RuleHit[]; readonly findings: readonly Finding[] }) {
  return reviewResult({
    packet: packet(options.hits),
    analysis: { findings: [...options.findings], dropped: [] },
    gate: { kept: options.findings, dropped: [] },
    dispositions: { problems: [], dropped: [], undecided: [] },
    candidates: [],
    model: "m",
    costUsd: null,
    correctionRound: "none",
    rejections: [],
    startedAt: Date.now(),
  });
}

test("a certain rule hit is reported even when the model returns nothing", () => {
  const result = resultFor({ hits: [certainHit], findings: [] });

  expect(result.findings.map((finding) => [finding.source, finding.path, finding.line])).toEqual([["rule", "src/keys.ts", 2]]);
});

test("a signal rule hit is not reported without the model", () => {
  const result = resultFor({ hits: [{ ...certainHit, level: "signal" }], findings: [] });

  expect(result.findings).toEqual([]);
  expect(result.statistics.signalRuleHits).toBe(1);
});

test("a certain finding survives the cap when the model returns many low findings", () => {
  const many = Array.from({ length: 15 }, (_, index) => modelFinding(index * 10 + 1));
  const result = resultFor({ hits: [certainHit], findings: many });

  expect(result.findings).toHaveLength(10);
  expect(result.findings[0]?.source).toBe("rule");
});
