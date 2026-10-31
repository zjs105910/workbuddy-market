import { expect, test } from "bun:test";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { buildRuntimeBundle } from "./bundle";

test("the published bundle excludes build paths and parses TypeScript after relocation", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "shadowclone-bundle-"));
  try {
    const entryPoint = path.join(directory, "source/entry.ts");
    const compiler = Bun.resolveSync("typescript", import.meta.dir);
    await Bun.write(entryPoint, [
      `import ts from ${JSON.stringify(compiler)};`,
      'const source = ts.createSourceFile("sample.ts", "export const value = 1;", ts.ScriptTarget.Latest, true);',
      "console.log(JSON.stringify({ statements: source.statements.length }));",
    ].join("\n"));
    const bundle = await buildRuntimeBundle(entryPoint);
    const text = await bundle.text();
    expect(text).not.toContain(process.cwd());
    expect(text).not.toContain(os.homedir());
    expect(text).not.toContain(path.dirname(compiler));
    const installed = path.join(directory, "installed/cli.js");
    await Bun.write(installed, bundle);
    const run = Bun.spawn([process.execPath, installed], { stdout: "pipe", stderr: "pipe" });
    expect(await new Response(run.stdout).json()).toEqual({ statements: 1 });
    expect(await run.exited).toBe(0);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
