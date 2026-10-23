import { expect, test } from "bun:test";
import { parseDiff } from "../collect/diff";
import { limitToChanges, subtractBase } from "./compare";

test("an error that existed at the base is not new even when its line moved", () => {
  const base = [{ tool: "typecheck", path: "src/a.ts", line: 10, message: "error TS2304: Cannot find name 'x'." }];
  const head = [
    { tool: "typecheck", path: "src/a.ts", line: 14, message: "error TS2304: Cannot find name 'x'." },
    { tool: "typecheck", path: "src/b.ts", line: 3, message: "error TS2322: Type 'string' is not assignable to type 'number'." },
  ];

  expect(subtractBase({ head, base }).map((diagnostic) => diagnostic.path)).toEqual(["src/b.ts"]);
});

test("a second copy of a base error at the head is new", () => {
  const error = { tool: "typecheck", path: "src/a.ts", line: 1, message: "error TS2304: Cannot find name 'x'." };

  expect(subtractBase({ head: [error, { ...error, line: 9 }], base: [error] })).toHaveLength(1);
});

test("a lint diagnostic on an unchanged line is left out", () => {
  const files = parseDiff(
    ["diff --git a/src/a.ts b/src/a.ts", "--- a/src/a.ts", "+++ b/src/a.ts", "@@ -1,2 +1,2 @@", " const a = 1;", "-const b = 2;", "+let b = 2;", ""].join("\n"),
  );
  const diagnostics = [
    { tool: "eslint", path: "src/a.ts", line: 1, message: "old problem" },
    { tool: "eslint", path: "src/a.ts", line: 2, message: "'b' is never reassigned. (prefer-const)" },
  ];

  expect(limitToChanges({ diagnostics, files, scope: "changed-lines" }).map((diagnostic) => diagnostic.line)).toEqual([2]);
});
