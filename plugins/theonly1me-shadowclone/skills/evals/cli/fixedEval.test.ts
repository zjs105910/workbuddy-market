import { expect, test } from "bun:test";
import { parseFixedArguments } from "./fixedEval";

const protocol = ["--protocol", "preference-respect-v1"];

test("fixed preparation requires explicit host, model, effort, and a private output path", () => {
  const options = parseFixedArguments([...protocol, "--phase", "prepare", "--engine", "codex", "--model", "synthetic-model", "--effort", "high", "--output-directory", "/private/tmp/fixed-eval"]);
  expect(options).toMatchObject({ phase: "prepare", repetitions: 3, engine: "codex", effort: "high" });
  expect(() => parseFixedArguments([...protocol, "--phase", "prepare", "--output-directory", "out"])).toThrow();
});

test("only native execution requires explicit authorization, and its frozen configuration cannot be overridden", () => {
  expect(() => parseFixedArguments([...protocol, "--phase", "run", "--suite-file", "suite.json"])).toThrow();
  expect(parseFixedArguments([...protocol, "--phase", "run", "--suite-file", "suite.json", "--yes"])).toMatchObject({ phase: "run", yes: true });
  expect(() => parseFixedArguments([...protocol, "--phase", "run", "--suite-file", "suite.json", "--yes", "--model", "other"])).toThrow();
  expect(parseFixedArguments([...protocol, "--phase", "validate", "--suite-file", "suite.json"])).toMatchObject({ phase: "validate" });
  expect(parseFixedArguments([...protocol, "--phase", "compare", "--baseline-file", "base.json", "--candidate-file", "candidate.json"])).toMatchObject({ phase: "compare" });
});
