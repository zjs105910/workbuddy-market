import { expect, test } from "bun:test";
import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { parseDiff } from "../collect/diff";
import type { Evidence, Finding } from "../types";
import { gateFindings } from "./index";

async function checkoutWith(files: Readonly<Record<string, string>>): Promise<string> {
  const root = await mkdtemp(path.join(os.tmpdir(), "shadowclone-evidence-"));

  for (const [filePath, content] of Object.entries(files)) {
    await Bun.write(path.join(root, filePath), content);
  }

  return root;
}

function finding(evidence: readonly Evidence[], line = 3): Finding {
  return {
    path: "src/total.ts",
    line,
    severity: "high",
    category: "correctness",
    source: "investigation",
    title: "Total skips the discount",
    explanation: "The total ignores the discount.",
    failureScenario: "A 10% coupon charges the full price.",
    evidence: [...evidence],
    rule: null,
    suggestion: null,
    refutation: "The refuter found no other discount path.",
    candidates: [],
  };
}

const source = "export function total(price: number, discount: number): number {\n  const net = price;\n  return net;\n}\n";

async function gate(options: { readonly findings: readonly Finding[]; readonly pages?: Readonly<Record<string, string>> }) {
  const checkout = await checkoutWith({ "src/total.ts": source });

  return gateFindings({
    findings: options.findings,
    sources: {
      checkout,
      files: parseDiff(""),
      ruleHits: [],
      toolchain: [],
      fetchText: async (url) => options.pages?.[url] ?? null,
    },
  });
}

test("a finding whose quote is at the cited line is kept", async () => {
  const result = await gate({ findings: [finding([{ source: "code", location: "src/total.ts:2", quote: "const net = price;" }])] });

  expect([result.kept.length, result.dropped]).toEqual([1, []]);
});

test("a finding that quotes code which is not at the cited line is dropped with the reason", async () => {
  const result = await gate({ findings: [finding([{ source: "code", location: "src/total.ts:2", quote: "const net = price - discount;" }])] });

  expect(result.kept).toEqual([]);
  expect(result.dropped[0]?.reason).toBe("the quoted code is not at `src/total.ts:2`");
});

test("evidence that points outside the checkout is not read", async () => {
  const result = await gate({ findings: [finding([{ source: "code", location: "../../etc/hosts:1", quote: "localhost" }])] });

  expect(result.dropped[0]?.reason).toBe("`../../etc/hosts:1` is not a file and line at the head");
});

test("a finding at a line that does not exist is dropped", async () => {
  const result = await gate({ findings: [finding([{ source: "code", location: "src/total.ts:2", quote: "const net = price;" }], 90)] });

  expect(result.dropped[0]?.reason).toBe("`src/total.ts:90` does not exist at the head");
});

test("a documentation quote that is not on the page is removed, and the code evidence keeps the finding", async () => {
  const url = "https://docs.example.com/money";
  const result = await gate({
    findings: [
      finding([
        { source: "code", location: "src/total.ts:2", quote: "const net = price;" },
        { source: "doc", location: url, quote: "Discounts apply before tax." },
      ]),
    ],
    pages: { [url]: "Totals round to cents." },
  });

  expect(result.kept[0]?.evidence.map((item) => item.source)).toEqual(["code"]);
});

test("a finding with only documentation evidence is dropped", async () => {
  const url = "https://docs.example.com/money";
  const result = await gate({ findings: [finding([{ source: "doc", location: url, quote: "Discounts apply before tax." }])], pages: { [url]: "Discounts apply before tax." } });

  expect(result.dropped[0]?.reason).toBe("no evidence points at the code or the diff");
});
