import { expect, test } from "bun:test";
import { runHostCommand, defaultConfig, writeConfig, createProjectPaths } from "@shadowclone/core";
import { mkdir, mkdtemp, rm, symlink } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { installLiveClone } from "./install";
import { uninstallLiveClone } from "./uninstall";
import { artifactRelativePaths, removeArtifacts } from "@shadowclone/environment";

test("uninstall preserves user edits and a manifest cannot authorize an unrelated file", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "shadowclone-ownership-"));

  try {
    const repository = path.join(root, "repository");

    await mkdir(repository);
    await runHostCommand({
      arguments: ["git", "init", "--quiet"],
      cwd: repository,
    });

    const paths = createProjectPaths({
      homeDirectory: root,
      platform: "darwin",
    });

    await writeConfig({ config: defaultConfig, configPath: paths.configFile });
    await installLiveClone({
      cwd: repository,
      paths,
      configPath: paths.configFile,
      managedConfigPath: null,
    });

    const target = path.join(repository, artifactRelativePaths.agent);

    await Bun.write(target, "user-maintained agent");
    await uninstallLiveClone({ cwd: repository, paths });

    expect(await Bun.file(target).text()).toBe("user-maintained agent");
    expect(
      await removeArtifacts({ directory: repository, artifacts: ["agent"] }),
    ).toBe(0);
    expect(await Bun.file(target).text()).toBe("user-maintained agent");
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("install refuses a symlinked agent directory", async () => {
  const root = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-install-link-"),
  );

  try {
    const repository = path.join(root, "repository");
    const outside = path.join(root, "outside");

    await mkdir(repository);
    await runHostCommand({
      arguments: ["git", "init", "--quiet"],
      cwd: repository,
    });
    await mkdir(outside);
    await symlink(outside, path.join(repository, ".claude"));

    const paths = createProjectPaths({
      homeDirectory: root,
      platform: "darwin",
    });

    await writeConfig({ config: defaultConfig, configPath: paths.configFile });

    await expect(
      installLiveClone({
        cwd: repository,
        paths,
        configPath: paths.configFile,
        managedConfigPath: null,
      }),
    ).rejects.toThrow("unsafe path");
    expect(
      await Bun.file(path.join(outside, "agents", "shadowclone.md")).exists(),
    ).toBeFalse();
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
