import { expect, test } from "bun:test";
import { entropyThresholdBitsPerCharacter, shannonEntropy } from "./entropy";
import { redactSecrets } from "./index";

const homeDirectory = "/Users/developer";

test("an empty string carries no entropy", () => {
  expect(shannonEntropy("")).toBe(0);
});

test("a single repeated character carries no entropy", () => {
  expect(shannonEntropy("aaaaaaaa")).toBe(0);
});

test("distinct characters reach the log2 ceiling", () => {
  expect(shannonEntropy("abcd")).toBe(Math.log2(4));
  expect(shannonEntropy("abcdefgh")).toBe(Math.log2(8));
});

test("an uneven distribution falls below the ceiling", () => {
  expect(shannonEntropy("aaab")).toBeCloseTo(0.8113, 4);
});

test("the threshold is unreachable below twenty three distinct characters", () => {
  expect(Math.log2(22)).toBeLessThan(entropyThresholdBitsPerCharacter);
  expect(Math.log2(23)).toBeGreaterThan(entropyThresholdBitsPerCharacter);
});

test("redacts a high entropy token no vendor rule matches", () => {
  const secret = ["int", "9fKw2QzR7mVpL4xN8tYbH3sJ6dGcA1eZ5uT"].join("_");
  const redacted = redactSecrets({ text: secret, homeDirectory });

  expect(redacted).not.toContain(secret);
  expect(redacted).toContain("[redacted:shannon-entropy]");
});

test("keeps the assignment name and redacts only the value", () => {
  const redacted = redactSecrets({
    text: "export INTERNAL_API=Xq2mZpR8vNwL4tJ6yHbF3sQ9dG",
    homeDirectory,
  });

  expect(redacted).toContain("export INTERNAL_API=");
  expect(redacted).toContain("[redacted:shannon-entropy]");
});

test("leaves a low entropy identifier untouched", () => {
  const identifier = "computeSourceMarkerHealth";

  expect(redactSecrets({ text: identifier, homeDirectory })).toBe(identifier);
});

test("leaves a mid token equals sign to the long blob rule", () => {
  const redacted = redactSecrets({
    text: "Bkx2VBx7BisAV5M+7v+b=vo5DdbCz6F+UqtwxqOP3S3U",
    homeDirectory,
  });

  expect(redacted).toContain("[redacted:high-entropy-string]");
});

test("keeps no part of a token that carries no public prefix", () => {
  const redacted = redactSecrets({
    text: "k7Xq2mZpR8vNwL4tJ6yHbF3sQ9dGcA1e",
    homeDirectory,
  });

  expect(redacted).toBe("[redacted:shannon-entropy]");
});
