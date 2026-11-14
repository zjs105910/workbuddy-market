import { expect, test } from "bun:test";
import { matchCredential } from "./credentials";
import { builtInRules } from "./index";

test("every built-in rule matches its own hit example and not its miss example", () => {
  const failures = builtInRules.flatMap((rule) => [
    ...(rule.pattern.test(rule.examples.hit) ? [] : [`${rule.id} misses its hit example`]),
    ...(rule.pattern.test(rule.examples.miss) ? [`${rule.id} matches its miss example`] : []),
  ]);

  expect(failures).toEqual([]);
});

test("built-in rule ids are unique", () => {
  const ids = builtInRules.map((rule) => rule.id);

  expect(new Set(ids).size).toBe(ids.length);
});

test("a cloud access key in an added line is a certain credential", () => {
  const key = ["AKIA", "Q3EGRZ7X2WN4LMPB"].join("");

  expect(matchCredential(`const accessKey = "${key}";`)).toEqual({ label: "aws-access-key-id", level: "certain" });
});

test("a documented placeholder key is not reported as a credential", () => {
  const key = ["AKIA", "IOSFODNN7", "EXAMPLE"].join("");

  expect(matchCredential(`aws_access_key_id = ${key}`)).toBeNull();
});

test("a payment test-mode key is only a signal", () => {
  const key = ["sk", "test", "4eC39HqLyjWDarjtT1zdp7dc"].join("_");

  expect(matchCredential(`const stripeKey = "${key}";`)?.level).toBe("signal");
});

test("a database URL without a password is not a credential", () => {
  expect(matchCredential('const url = "postgres://localhost:5432/app";')).toBeNull();
});
