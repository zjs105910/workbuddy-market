import { expect, test } from "bun:test";
import { parseDiagnostics } from "./parsers";

const roots = ["/work/head", "/private/work/head"];

test("TypeScript compiler output becomes a diagnostic at its file and line", () => {
  const output = "src/order.ts(12,7): error TS2345: Argument of type 'string' is not assignable to parameter of type 'number'.";

  expect(parseDiagnostics({ tool: "typecheck", parser: "paren", output, roots })).toEqual([
    { tool: "typecheck", path: "src/order.ts", line: 12, message: "error TS2345: Argument of type 'string' is not assignable to parameter of type 'number'." },
  ]);
});

test(".NET build output drops the project suffix and the absolute root", () => {
  const output = "/work/head/src/Api/Orders.cs(40,9): error CS0103: The name 'total' does not exist in the current context [/work/head/src/Api/Api.csproj]";

  expect(parseDiagnostics({ tool: "dotnet build", parser: "paren", output, roots })).toEqual([
    { tool: "dotnet build", path: "src/Api/Orders.cs", line: 40, message: "error CS0103: The name 'total' does not exist in the current context" },
  ]);
});

test("Maven output under the real path of the root is relative to the root", () => {
  const output = "[ERROR] /private/work/head/src/main/java/App.java:[8,20] cannot find symbol";

  expect(parseDiagnostics({ tool: "maven compile", parser: "maven", output, roots })).toEqual([
    { tool: "maven compile", path: "src/main/java/App.java", line: 8, message: "cannot find symbol" },
  ]);
});

test("Kotlin compiler lines from Gradle are parsed", () => {
  const output = "e: file:///work/head/app/src/Main.kt:3:5 Unresolved reference: total";

  expect(parseDiagnostics({ tool: "gradle classes", parser: "gradle", output, roots })).toEqual([
    { tool: "gradle classes", path: "app/src/Main.kt", line: 3, message: "Unresolved reference: total" },
  ]);
});

test("ESLint JSON output keeps the rule id", () => {
  const output = JSON.stringify([
    { filePath: "/work/head/src/a.ts", messages: [{ line: 4, message: "'total' is never reassigned.", ruleId: "prefer-const" }] },
  ]);

  expect(parseDiagnostics({ tool: "eslint", parser: "eslint-json", output, roots })).toEqual([
    { tool: "eslint", path: "src/a.ts", line: 4, message: "'total' is never reassigned. (prefer-const)" },
  ]);
});

test("Pyright output is parsed", () => {
  const output = '  /work/head/app/main.py:9:12 - error: "total" is not defined (reportUndefinedVariable)';

  expect(parseDiagnostics({ tool: "pyright", parser: "pyright", output, roots })).toEqual([
    { tool: "pyright", path: "app/main.py", line: 9, message: 'error: "total" is not defined (reportUndefinedVariable)' },
  ]);
});

test("a diagnostic for a file outside the root is dropped", () => {
  const output = "/usr/lib/node_modules/typescript/lib/lib.d.ts(1,1): error TS1: outside";

  expect(parseDiagnostics({ tool: "typecheck", parser: "paren", output, roots })).toEqual([]);
});
