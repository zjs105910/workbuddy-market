import { expect, test } from "bun:test";
import { mkdir, mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { defaultConfig, writeConfig, createProjectPaths } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";
import { installLiveClone } from "./install";
import { readInstallations } from "@shadowclone/environment";
import { uninstallLiveClone } from "./uninstall";

const agentRelativePath = path.join(".claude", "agents", "shadowclone.md");
const skillDirectory = path.join(".claude", "skills", "shadowclone");

async function installed(options: {
  readonly existingExclude?: string;
}): Promise<{
  readonly targetDirectory: string;
  readonly paths: ProjectPaths;
  readonly excludePath: string;
}> {
  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-uninstall-home-"),
  );
  const targetDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-uninstall-repo-"),
  );
  const init = Bun.spawn({
    cmd: ["git", "-C", targetDirectory, "init"],
    stdout: "ignore",
    stderr: "ignore",
  });

  expect(await init.exited).toBe(0);

  const excludePath = path.join(targetDirectory, ".git", "info", "exclude");

  if (options.existingExclude !== undefined) {
    await Bun.write(excludePath, options.existingExclude);
  }

  const paths = createProjectPaths({ homeDirectory, platform: "darwin" });

  await writeConfig({ config: defaultConfig, configPath: paths.configFile });
  await installLiveClone({
    cwd: targetDirectory,
    configPath: paths.configFile,
    paths,
    managedConfigPath: null,
    autoDelegate: true,
  });

  return { targetDirectory, paths, excludePath };
}

test("uninstall removes the repository artifacts and its manifest record", async () => {
  const { targetDirectory, paths } = await installed({});
  const unrelated = path.join(targetDirectory, ".claude", "agents", "other.md");

  await mkdir(path.dirname(unrelated), { recursive: true });
  await Bun.write(unrelated, "Someone else's agent.");

  await uninstallLiveClone({ cwd: targetDirectory, paths });

  expect(
    await Bun.file(path.join(targetDirectory, agentRelativePath)).exists(),
  ).toBeFalse();
  expect(
    await Bun.file(
      path.join(targetDirectory, skillDirectory, "SKILL.md"),
    ).exists(),
  ).toBeFalse();
  expect(await Bun.file(unrelated).exists()).toBeTrue();
  expect(
    (await readInstallations(paths.installationsFile)).installations,
  ).toEqual([]);
});

test("uninstall removes only the exclude lines the installer added", async () => {
  const existing = ".claude/agents/other.md\nbuild/\n";
  const { targetDirectory, paths, excludePath } = await installed({
    existingExclude: existing,
  });

  await uninstallLiveClone({ cwd: targetDirectory, paths });

  const excludes = await Bun.file(excludePath).text();

  expect(excludes).toContain(".claude/agents/other.md");
  expect(excludes).toContain("build/");
  expect(excludes).not.toContain("shadowclone");
});

test("uninstall runs twice without failing", async () => {
  const { targetDirectory, paths } = await installed({});

  await uninstallLiveClone({ cwd: targetDirectory, paths });
  await uninstallLiveClone({ cwd: targetDirectory, paths });

  expect(
    await Bun.file(path.join(targetDirectory, agentRelativePath)).exists(),
  ).toBeFalse();
});
