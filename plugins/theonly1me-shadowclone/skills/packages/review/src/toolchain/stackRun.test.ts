import { expect, test } from "bun:test";
import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { parseDiff } from "../collect/diff";
import { runStack } from "./stackRun";
import type { Stack } from "./types";

async function worktreeWith(diagnostics: string) {
  const root = await mkdtemp(path.join(os.tmpdir(), "shadowclone-stack-"));
  await Bun.write(path.join(root, "diagnostics.txt"), diagnostics);

  return { root, roots: [root] };
}

const printingStack: Stack = {
  id: "fixture",
  sources: /\.ts$/,
  detect: () => true,
  install: () => null,
  commands: [
    {
      tool: "typecheck",
      scope: "new-in-head",
      parser: "paren",
      command: () => ["sh", "-c", "cat diagnostics.txt; exit 2"],
    },
  ],
};

const files = parseDiff(
  ["diff --git a/src/a.ts b/src/a.ts", "--- a/src/a.ts", "+++ b/src/a.ts", "@@ -1 +1 @@", "-export const a = 1;", "+export const a = 2;", ""].join("\n"),
);

test("a type error that also exists at the base is not reported", async () => {
  const existing = "src/old.ts(3,1): error TS2304: Cannot find name 'legacy'.";
  const head = await worktreeWith(`${existing}\nsrc/a.ts(1,14): error TS2322: Type 'number' is not assignable to type 'string'.\n`);
  const base = await worktreeWith(`${existing}\n`);

  const [report] = await runStack({ stack: printingStack, head, base: async () => base, files, onProgress: () => {} });

  expect(report?.diagnostics.map((diagnostic) => diagnostic.path)).toEqual(["src/a.ts"]);
  expect(report?.detail).toBe("1 new of 2 at the head");
});

test("a command that fails without printing diagnostics is reported as failed, not clean", async () => {
  const head = await worktreeWith("Cannot read configuration\n");

  const [report] = await runStack({ stack: printingStack, head, base: async () => head, files, onProgress: () => {} });

  expect([report?.status, report?.detail]).toEqual(["failed", "Cannot read configuration"]);
});

test("a missing tool is reported as skipped with its name", async () => {
  const head = await worktreeWith("");
  const missingTool: Stack = {
    ...printingStack,
    commands: [{ tool: "absent", scope: "new-in-head", parser: "paren", command: () => ["shadowclone-absent-tool"] }],
  };

  const [report] = await runStack({ stack: missingTool, head, base: async () => head, files, onProgress: () => {} });

  expect([report?.status, report?.detail]).toEqual(["skipped", "shadowclone-absent-tool is not installed"]);
});
