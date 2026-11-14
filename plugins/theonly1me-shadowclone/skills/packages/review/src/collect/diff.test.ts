import { expect, test } from "bun:test";
import { parseDiff } from "./diff";

const modified = [
  "diff --git a/src/order.ts b/src/order.ts",
  "index 1111111..2222222 100644",
  "--- a/src/order.ts",
  "+++ b/src/order.ts",
  "@@ -10,4 +10,5 @@ export function total() {",
  "   const items = read();",
  "-  return sum(items);",
  "+  const taxed = tax(items);",
  "+  return sum(taxed);",
  "   // end",
  " }",
  "",
].join("\n");

test("a hunk's comment range is the whole right side of the hunk", () => {
  const [file] = parseDiff(modified);

  expect(file?.ranges).toEqual([[10, 14]]);
});

test("added lines carry their line numbers at the head", () => {
  const [file] = parseDiff(modified);

  expect(file?.added).toEqual([
    { line: 11, text: "  const taxed = tax(items);" },
    { line: 12, text: "  return sum(taxed);" },
  ]);
});

test("a removed SQL comment line inside a hunk is a removal, not a file header", () => {
  const [file] = parseDiff(
    [
      "diff --git a/db/schema.sql b/db/schema.sql",
      "--- a/db/schema.sql",
      "+++ b/db/schema.sql",
      "@@ -1,2 +1,1 @@",
      "--- old note",
      " CREATE TABLE users (id int);",
      "",
    ].join("\n"),
  );

  expect([file?.path, file?.changedLines, file?.ranges]).toEqual(["db/schema.sql", 1, [[1, 1]]]);
});

test("a deleted file keeps its old path and has no comment range", () => {
  const [file] = parseDiff(
    [
      "diff --git a/src/old.ts b/src/old.ts",
      "deleted file mode 100644",
      "--- a/src/old.ts",
      "+++ /dev/null",
      "@@ -1,2 +0,0 @@",
      "-export const a = 1;",
      "-export const b = 2;",
      "",
    ].join("\n"),
  );

  expect([file?.path, file?.deleted, file?.ranges]).toEqual(["src/old.ts", true, []]);
});

test("a renamed file uses its new path", () => {
  const [file] = parseDiff(
    [
      "diff --git a/src/a.ts b/src/b.ts",
      "similarity index 90%",
      "rename from src/a.ts",
      "rename to src/b.ts",
      "--- a/src/a.ts",
      "+++ b/src/b.ts",
      "@@ -1 +1 @@",
      "-export const name = 1;",
      "+export const name = 2;",
      "",
    ].join("\n"),
  );

  expect(file?.path).toBe("src/b.ts");
});
