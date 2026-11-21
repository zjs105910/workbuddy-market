import { expect, test } from "bun:test";
import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { createProjectPaths } from "@shadowclone/core";
import { ensureHookRunner } from "./hookRunner";

test("private hook launcher runs without shadowclone on PATH and preserves edits", async () => {
  const homeDirectory = await mkdtemp(path.join(os.tmpdir(), "shadowclone-hook-runner-"));
  const paths = createProjectPaths({ homeDirectory, platform: "darwin" });
  const entry = path.join(homeDirectory, "synthetic-cli.ts");
  await Bun.write(entry, "console.log(JSON.stringify(process.argv.slice(2)))\n");

  await ensureHookRunner({ paths, executable: process.execPath, entry });
  const filePath = path.join(paths.shadowcloneDirectory, "bin", "shadowclone");
  const run = Bun.spawnSync({
    cmd: ["/bin/sh", filePath, "hook", "native-start"],
    env: { PATH: "/usr/bin:/bin", HOME: homeDirectory },
  });

  expect(run.exitCode).toBe(0);
  expect(new TextDecoder().decode(run.stdout).trim()).toBe('["hook","native-start"]');

  await Bun.write(filePath, "echo user edit\n");
  await expect(ensureHookRunner({ paths, executable: process.execPath, entry }))
    .rejects.toThrow("edited");
  expect(await Bun.file(filePath).text()).toBe("echo user edit\n");
});
