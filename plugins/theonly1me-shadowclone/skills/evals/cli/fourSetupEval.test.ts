import { expect, test } from "bun:test";
import { parseFourSetupArguments } from "./fourSetupEval";

test("four-setup CLI requires explicit model identities and separate authorization for learning and scoring", () => {
  expect(() => parseFourSetupArguments(["--protocol", "preference-respect-v2", "--phase", "learn", "--preparation-file", "/private/preparation.json"])).toThrow();
  expect(() => parseFourSetupArguments(["--protocol", "preference-respect-v2", "--phase", "run", "--suite-file", "/private/suite.json"])).toThrow();
  expect(() => parseFourSetupArguments(["--protocol", "preference-respect-v2", "--phase", "prepare-environments", "--output-directory", "/private/new"])).toThrow();
  const options = parseFourSetupArguments(["--protocol", "preference-respect-v2", "--phase", "prepare-environments", "--output-directory", "/private/new",
    "--engine", "codex", "--model", "synthetic-model", "--effort", "medium"]);
  expect(options?.phase === "prepare-environments" && options.maximumCalls).toBe(16);
});
