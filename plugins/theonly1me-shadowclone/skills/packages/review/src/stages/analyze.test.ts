import { expect, test } from "bun:test";
import type { EngineRunOptions } from "@shadowclone/agents";
import { collectReview } from "../collect";
import { createGitFixture } from "../collect/gitFixture";
import { engineRun } from "../engineFixture";
import type { Finding } from "../types";
import { analyzeStage } from "./analyze";
import type { PacketFile } from "./schemas";

async function packetWithSignal(): Promise<{ readonly packet: PacketFile; readonly checkout: string }> {
  const fixture = await createGitFixture();
  await fixture.write({ "src/total.ts": "export function total(price: number): number {\n  return price;\n}\n" });
  const baseSha = fixture.commit("base");
  await fixture.write({ "src/total.ts": "export function total(price: number, discount: number): number {\n  const net = price;\n  return net;\n}\n" });
  const headSha = fixture.commit("head");
  const context = await collectReview({
    checkout: fixture.directory,
    facts: { repository: "example/app", number: 1, title: "t", body: "", baseRefName: "main", baseSha, headSha },
  });
  const signal = { ruleId: "js-eval", level: "signal" as const, severity: "high" as const, category: "security" as const, title: "Code built from a string", failure: "f", path: "src/total.ts", line: 2 };

  return { packet: { version: 1, context, ruleHits: [signal], reports: [] }, checkout: fixture.directory };
}

function finding(quote: string): Finding {
  return {
    path: "src/total.ts",
    line: 2,
    severity: "high",
    category: "correctness",
    source: "investigation",
    title: "The discount is never applied",
    explanation: "The new parameter is unused.",
    failureScenario: "total(100, 10) returns 100.",
    evidence: [{ source: "code", location: "src/total.ts:2", quote }],
    rule: null,
    suggestion: null,
    refutation: "No other code applies the discount.",
    candidates: [],
  };
}

function scriptedRunner(answers: readonly unknown[], prompts: string[]) {
  return async (run: EngineRunOptions) => {
    prompts.push(run.prompt);
    const answer = answers[prompts.length - 1];

    return answer instanceof Error ? engineRun({ isError: true, errorMessage: answer.message }) : engineRun({ structured: answer });
  };
}

test("a wrong quote and a missing decision get one correction round, and the corrected answer is kept", async () => {
  const { packet, checkout } = await packetWithSignal();
  const prompts: string[] = [];
  const result = await analyzeStage({
    packet,
    checks: null,
    checkout,
    reviewModel: {
      runner: scriptedRunner(
        [
          { findings: [finding("const net = price - discount;")], dropped: [] },
          { findings: [finding("const net = price;")], dropped: [{ id: "S1", reason: "No string reaches eval." }] },
        ],
        prompts,
      ),
      model: "m",
      effort: "high",
      network: false,
    },
  });

  expect(prompts).toHaveLength(2);
  expect(prompts[1]).toContain("the quoted code is not at `src/total.ts:2`");
  expect(prompts[1]).toContain("S1 have no decision");
  expect([result.statistics.correctionRound, result.findings.length, result.candidates.dropped.map((entry) => entry.id)]).toEqual(["ran", 1, ["S1"]]);
});

test("a clean first answer needs no correction round", async () => {
  const { packet, checkout } = await packetWithSignal();
  const prompts: string[] = [];
  const result = await analyzeStage({
    packet,
    checks: null,
    checkout,
    reviewModel: {
      runner: scriptedRunner([{ findings: [finding("const net = price;")], dropped: [{ id: "S1", reason: "constant" }] }], prompts),
      model: "m",
      effort: "high",
      network: false,
    },
  });

  expect([prompts.length, result.statistics.correctionRound]).toEqual([1, "none"]);
});

test("when the correction round fails, the first answer is judged as it was", async () => {
  const { packet, checkout } = await packetWithSignal();
  const result = await analyzeStage({
    packet,
    checks: null,
    checkout,
    reviewModel: {
      runner: scriptedRunner([{ findings: [finding("const net = price - discount;")], dropped: [] }, new Error("rate limited")], []),
      model: "m",
      effort: "high",
      network: false,
    },
  });

  expect([result.statistics.correctionRound, result.findings, result.candidates.undecided.map((entry) => entry.id)]).toEqual(["failed", [], ["S1"]]);
});

test("the result keeps the problems that started the correction round", async () => {
  const { packet, checkout } = await packetWithSignal();
  const result = await analyzeStage({
    packet,
    checks: null,
    checkout,
    reviewModel: {
      runner: scriptedRunner(
        [
          { findings: [finding("const net = price - discount;")], dropped: [{ id: "S1", reason: "constant" }] },
          { findings: [finding("const net = price;")], dropped: [{ id: "S1", reason: "constant" }] },
        ],
        [],
      ),
      model: "m",
      effort: "high",
      network: false,
    },
  });

  expect(result.rejections).toEqual(['Finding "The discount is never applied" at src/total.ts:2: the quoted code is not at `src/total.ts:2`.']);
});
