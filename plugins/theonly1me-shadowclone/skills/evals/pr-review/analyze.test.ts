import { expect, test } from "bun:test";
import { detectedIds, finalLabels } from "./analyze";

const judged = {
  caseId: "c01",
  kind: "defect" as const,
  findings: [{ id: "Fa", arm: "x" }, { id: "Fb", arm: "y" }],
  answers: [
    { judge: "opus", output: { findings: [{ id: "Fa", label: "real" as const }, { id: "Fb", label: "wrong" as const }], detected: ["Fa"] } },
    { judge: "sol", output: { findings: [{ id: "Fa", label: "real" as const }, { id: "Fb", label: "minor" as const }], detected: ["Fa", "Fb"] } },
  ],
};

test("a label counts only when both judges agree, and a disagreement waits for a blind tie-break", () => {
  expect([...finalLabels({ judged, tiebreaks: new Map() })]).toEqual([["Fa", "real"], ["Fb", "disputed"]]);
  expect(finalLabels({ judged, tiebreaks: new Map([["Fb", "wrong"]]) }).get("Fb")).toBe("wrong");
});

test("a known bug counts as found only when both judges name the same finding", () => {
  expect([...detectedIds(judged)]).toEqual(["Fa"]);
});
