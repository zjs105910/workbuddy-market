import { expect, test } from "bun:test";
import { mkdir, mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { defaultConfig, writeConfig, createProjectPaths } from "@shadowclone/core";
import { forgetAll } from "./forget";
import { installLiveClone } from "./install";

const agentRelativePath = path.join(".claude", "agents", "shadowclone.md");

test("forget all removes every recorded repository install", async () => {
  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-forget-installs-"),
  );
  const transcriptDirectory = path.join(homeDirectory, ".claude");

  await mkdir(transcriptDirectory, { recursive: true });
  await Bun.write(path.join(transcriptDirectory, "session.jsonl"), "source");

  const paths = createProjectPaths({ homeDirectory, platform: "darwin" });

  await writeConfig({ config: defaultConfig, configPath: paths.configFile });

  const repositories: string[] = [];

  for (const name of ["first", "second"]) {
    const targetDirectory = await mkdtemp(
      path.join(os.tmpdir(), `shadowclone-forget-${name}-`),
    );
    const init = Bun.spawn({
      cmd: ["git", "-C", targetDirectory, "init"],
      stdout: "ignore",
      stderr: "ignore",
    });

    expect(await init.exited).toBe(0);

    await installLiveClone({
      cwd: targetDirectory,
      configPath: paths.configFile,
      paths,
      managedConfigPath: null,
      autoDelegate: true,
    });
    repositories.push(targetDirectory);
  }

  for (const repository of repositories) {
    expect(
      await Bun.file(path.join(repository, agentRelativePath)).exists(),
    ).toBeTrue();
  }

  await forgetAll({ paths });

  for (const repository of repositories) {
    expect(
      await Bun.file(path.join(repository, agentRelativePath)).exists(),
    ).toBeFalse();
    expect(
      await Bun.file(
        path.join(repository, ".claude", "skills", "shadowclone", "SKILL.md"),
      ).exists(),
    ).toBeFalse();

    const excludes = await Bun.file(
      path.join(repository, ".git", "info", "exclude"),
    ).text();

    expect(excludes).not.toContain("shadowclone");
  }

  expect(await Bun.file(paths.installationsFile).exists()).toBeFalse();
  expect(
    await Bun.file(path.join(transcriptDirectory, "session.jsonl")).exists(),
  ).toBeTrue();
});
