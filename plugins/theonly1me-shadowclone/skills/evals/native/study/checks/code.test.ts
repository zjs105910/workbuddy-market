import { expect, test } from "bun:test";
import { fileLength, filePatterns, identifiers, introducedSyntax, optionsObject } from "./code";

const file = (before: string | null, after: string | null, path = "src/export/csv.ts") => ({ path, before, after });

test("comment and type checks ignore existing violations and non-code files", () => {
  const existing = "// existing note\nexport const rate = 1;\n";
  expect(introducedSyntax({ files: [file(existing, `${existing}export const other = 2;\n`)], check: "zero-comments" }).verdict).toBe("pass");
  expect(introducedSyntax({ files: [file(existing, `${existing}/** Explains. */\nexport const other = 2;\n`)], check: "zero-comments" }).verdict).toBe("fail");
  expect(introducedSyntax({ files: [file(null, "value as string;\n")], check: "type-safety" }).verdict).toBe("fail");
  expect(introducedSyntax({ files: [file(null, "# Notes\n", "README.md")], check: "zero-comments" }).verdict).toBe("not-applicable");
});

test("file length fails only when a changed file grows past the limit", () => {
  const lines = (count: number) => Array.from({ length: count }, (_, index) => `export const value${index} = ${index};`).join("\n");
  expect(fileLength({ files: [file(lines(150), lines(210))], limit: 200 }).verdict).toBe("fail");
  expect(fileLength({ files: [file(lines(250), lines(240))], limit: 200 }).verdict).toBe("pass");
});

test("options objects are required for new signatures with two or more parameters", () => {
  const before = "export function rowFor(options: { id: string }) { return options.id; }\n";
  expect(optionsObject({ files: [file(before, `${before}export function cell(value: string, width: number) { return value.padEnd(width); }\n`)] }).verdict).toBe("fail");
  expect(optionsObject({ files: [file(before, `${before}export const cell = (options: { value: string }) => options.value;\n`)] }).verdict).toBe("pass");
  expect(optionsObject({ files: [file(before, `${before}export const total = [1, 2].reduce((sum, value) => sum + value, 0);\n`)] }).verdict).toBe("not-applicable");
});

test("identifier checks flag new abbreviations and single letters", () => {
  const before = "const rows = [];\n";
  expect(identifiers({ files: [file(before, `${before}for (let i = 0; i < 2; i += 1) {}\n`)], denylist: ["cfg"] }).verdict).toBe("fail");
  expect(identifiers({ files: [file(before, `${before}const cfg = {};\n`)], denylist: ["cfg"] }).verdict).toBe("fail");
  expect(identifiers({ files: [file(before, `${before}const configuration = {};\n`)], denylist: ["cfg"] }).verdict).toBe("pass");
  expect(identifiers({ files: [file(before, before)], denylist: [] }).verdict).toBe("not-applicable");
});

test("file patterns flag newly introduced prose only", () => {
  const before = "# Tally\n\nExports usage.\n";
  const markdown = /\.md$/u;
  expect(filePatterns({ files: [file(before, `${before}Sync is gone \u2014 use export.\n`, "README.md")], filePattern: markdown, forbidden: [/\u2014/u] }).verdict).toBe("fail");
  expect(filePatterns({ files: [file(`${before}Old \u2014 note.\n`, `${before}Old \u2014 note.\nUse export.\n`, "README.md")], filePattern: markdown, forbidden: [/\u2014/u] }).verdict).toBe("pass");
  expect(filePatterns({ files: [file(null, "export const a = 1;\n")], filePattern: markdown, forbidden: [/\u2014/u] }).verdict).toBe("not-applicable");
});
