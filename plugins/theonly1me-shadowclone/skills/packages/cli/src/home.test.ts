import { expect, test } from "bun:test";
import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { defaultConfig, writeConfig, createProjectPaths } from "@shadowclone/core";
import { checkoutRoot } from "@shadowclone/core/testing";
import { showHome } from "./home";

test("the empty command names one useful next action", async () => {
  const homeDirectory = await mkdtemp(path.join(os.tmpdir(), "shadowclone-home-"));
  const paths = createProjectPaths({ homeDirectory, platform: "darwin" });
  const lines: string[] = [];

  await showHome({ paths, writeLine: (line) => lines.push(line) });
  expect(lines[0]).toContain("Run shadowclone init");

  lines.length = 0;
  await writeConfig({ config: defaultConfig, configPath: paths.configFile });
  await showHome({ paths, writeLine: (line) => lines.push(line) });
  expect(lines[0]).toContain("0 active learned rule(s)");
  expect(lines[1]).toContain("shadowclone install");
});

test("CLI failures print a bounded message without source code or a stack", async () => {
  const command = Bun.spawn([process.execPath, path.join(import.meta.dir, "main.ts"), "learn", "--apply"], {
    cwd: await checkoutRoot(), stdout: "pipe", stderr: "pipe",
  });
  const [output, error, exitCode] = await Promise.all([
    new Response(command.stdout).text(), new Response(command.stderr).text(), command.exited,
  ]);
  expect(exitCode).toBe(1);
  expect(output).toBe("");
  expect(error).toBe("learn --apply requires --deep\n");
});
