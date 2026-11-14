import { expect, test } from "bun:test";
import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { defaultConfig, writeConfig, createProjectPaths } from "@shadowclone/core";
import { learn } from "./learn";

test("never writes into the repository it is run from", async () => {
  const targetDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-repo-"),
  );
  const child = Bun.spawn({
    cmd: ["git", "-C", targetDirectory, "init", "--quiet"],
    stdout: "ignore",
    stderr: "ignore",
  });

  expect(await child.exited).toBe(0);

  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-learn-"),
  );
  const paths = createProjectPaths({ homeDirectory, platform: "darwin" });

  await writeConfig({ config: defaultConfig, configPath: paths.configFile });

  const previousDirectory = process.cwd();

  process.chdir(targetDirectory);

  try {
    await learn({
      configPath: paths.configFile,
      databasePath: paths.indexDatabase,
      paths,
      managedConfigPath: null,
    });
  } finally {
    process.chdir(previousDirectory);
  }

  expect(
    await Bun.file(
      path.join(targetDirectory, ".claude", "agents", "shadowclone.md"),
    ).exists(),
  ).toBeFalse();
  expect(
    await Bun.file(
      path.join(
        targetDirectory,
        ".claude",
        "skills",
        "shadowclone",
        "SKILL.md",
      ),
    ).exists(),
  ).toBeFalse();
});
