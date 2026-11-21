import { expect, test } from "bun:test";
import { parseDiff } from "../collect/diff";
import { checkBuiltInRules } from "./index";

function diffFor(options: { readonly path: string; readonly lines: readonly string[]; readonly start: number }): string {
  return [
    `diff --git a/${options.path} b/${options.path}`,
    `--- a/${options.path}`,
    `+++ b/${options.path}`,
    `@@ -${options.start},2 +${options.start},${options.lines.length} @@`,
    ...options.lines,
    "",
  ].join("\n");
}

test("a rule hit reports the line number at the head", () => {
  const files = parseDiff(
    diffFor({ path: "src/view.ts", start: 40, lines: [" const node = find();", "-node.textContent = message;", "+node.innerHTML = message;", " return node;"] }),
  );

  expect(checkBuiltInRules(files).map((hit) => [hit.ruleId, hit.path, hit.line])).toEqual([["js-html-injection", "src/view.ts", 41]]);
});

test("a removed line never produces a hit", () => {
  const files = parseDiff(
    diffFor({ path: "src/view.ts", start: 1, lines: ["-node.innerHTML = message;", "+node.textContent = message;"] }),
  );

  expect(checkBuiltInRules(files)).toEqual([]);
});

test("a rule only applies to the files of its language", () => {
  const files = parseDiff(diffFor({ path: "notes/review.md", start: 1, lines: ["+node.innerHTML = message;"] }));

  expect(checkBuiltInRules(files)).toEqual([]);
});

test("lockfiles are not checked", () => {
  const key = ["AKIA", "Q3EGRZ7X2WN4LMPB"].join("");
  const files = parseDiff(diffFor({ path: "package-lock.json", start: 1, lines: [`+  "token": "${key}"`] }));

  expect(checkBuiltInRules(files)).toEqual([]);
});

test("one rule reports at most five lines of one file", () => {
  const lines = Array.from({ length: 8 }, (_, index) => `+node${index}.innerHTML = message;`);
  const files = parseDiff(diffFor({ path: "src/view.ts", start: 1, lines }));

  expect(checkBuiltInRules(files)).toHaveLength(5);
});
