import { expect, test } from "bun:test";
import { checkDispositions, type ReviewCandidate } from "./candidates";
import type { Finding } from "./types";

const candidates: readonly ReviewCandidate[] = [
  { id: "S1", kind: "rule", path: "src/a.ts", line: 3, title: "js-eval: Code built from a string at runtime" },
  { id: "T1", kind: "toolchain", path: "src/b.ts", line: 9, title: "typecheck: error TS2322" },
];

function findingRaising(ids: readonly string[]): Finding {
  return {
    path: "src/b.ts",
    line: 9,
    severity: "high",
    category: "correctness",
    source: "toolchain",
    title: "Wrong type reaches the total",
    explanation: "e",
    failureScenario: "f",
    evidence: [{ source: "toolchain", location: "src/b.ts:9", quote: "TS2322" }],
    rule: null,
    suggestion: null,
    refutation: "r",
    candidates: [...ids],
  };
}

test("an answer that raises one candidate and drops the other with a reason passes", () => {
  const check = checkDispositions({ findings: [findingRaising(["T1"])], dropped: [{ id: "S1", reason: "The string is a constant." }], candidates });

  expect([check.problems, check.dropped.map((entry) => entry.id), check.undecided]).toEqual([[], ["S1"], []]);
});

test("a candidate with no decision is named so the correction round can ask for it", () => {
  const check = checkDispositions({ findings: [], dropped: [{ id: "S1", reason: "constant" }], candidates });

  expect(check.problems).toEqual(["T1 have no decision. Raise each one in a finding or drop it with a reason."]);
  expect(check.undecided.map((entry) => entry.id)).toEqual(["T1"]);
});

test("an invented id and an id with two decisions are both rejected", () => {
  const check = checkDispositions({
    findings: [findingRaising(["T1", "S9"])],
    dropped: [{ id: "T1", reason: "duplicate" }, { id: "S1", reason: "constant" }],
    candidates,
  });

  expect(check.problems).toEqual([
    "S9 are not candidate ids in the packet.",
    "T1 have more than one decision. Raise each id in one finding or drop it once.",
  ]);
});
