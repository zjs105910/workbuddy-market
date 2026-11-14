import { expect, test } from "bun:test";
import { introducesViolation } from "./checks";

const file = (before: string | null, after: string | null) => ({ path: "value.ts", before, after });
const existing = "// Existing rationale\nexport const value = input as string;\n";

test("unchanged existing comments and assertions do not count as introduced", () => {
  const changed = file(existing, `${existing}export const size = 2;\n`);
  expect(introducesViolation({ file: changed, criterion: { check: "zero-comments" } })).toBe(false);
  expect(introducesViolation({ file: changed, criterion: { check: "type-safety" } })).toBe(false);
});

test("new comments and assertions count even when the old file already has them", () => {
  const changed = file(existing, `${existing}// Another rationale\nexport const next = other as string;\n`);
  expect(introducesViolation({ file: changed, criterion: { check: "zero-comments" } })).toBe(true);
  expect(introducesViolation({ file: changed, criterion: { check: "type-safety" } })).toBe(true);
});

test("const assertions remain allowed and long files are flagged only when they grow", () => {
  expect(introducesViolation({ file: file(null, "export const values = [1, 2] as const;\n"), criterion: { check: "type-safety" } })).toBe(false);
  const lines = (count: number) => Array.from({ length: count }, (_, index) => `export const value${index} = ${index};`).join("\n");
  expect(introducesViolation({ file: file(lines(150), lines(210)), criterion: { check: "file-length" } })).toBe(true);
  expect(introducesViolation({ file: file(lines(250), lines(240)), criterion: { check: "file-length" } })).toBe(false);
});
