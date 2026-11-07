import { expect, test } from "bun:test";
import { parseStudyArguments } from "./studyEval";

const base = ["--protocol", "preference-study-v1", "--yes"];

test("run accepts an arm filter and concurrency", () => {
  const options = parseStudyArguments([...base, "--phase", "run", "--suite-file", "s.json", "--output-directory", "out", "--arms", "deep,bare", "--concurrency", "4"]);
  expect(options).toMatchObject({ phase: "run", arms: ["deep", "bare"], concurrency: 4 });
});

test("report accepts a base receipt and validate accepts report-only", () => {
  expect(parseStudyArguments([...base, "--phase", "report", "--suite-file", "s.json", "--output-directory", "out", "--coverage-file", "c.json", "--base-receipt-file", "r.json"]))
    .toMatchObject({ phase: "report", baseReceiptFile: "r.json" });
  expect(parseStudyArguments([...base, "--phase", "validate", "--suite-file", "s.json", "--output-directory", "out", "--report-only"]))
    .toMatchObject({ phase: "validate", reportOnly: true });
});

test("derive names the agent and prepare rejects unknown stages", () => {
  expect(parseStudyArguments([...base, "--phase", "derive", "--preparation-file", "p.json", "--suite-file", "s.json", "--engine", "claude-code"]))
    .toMatchObject({ phase: "derive", engine: "claude-code" });
  expect(() => parseStudyArguments([...base, "--phase", "prepare", "--stage", "unknown", "--preparation-file", "p.json"])).toThrow();
});
