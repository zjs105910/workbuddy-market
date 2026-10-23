import { expect, test } from "bun:test";
import { mkdir, mkdtemp, symlink, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { createProjectPaths } from "@shadowclone/core";
import { forgetAll } from "./forget";
import { writeInstallations } from "@shadowclone/environment";

async function scratch(prefix: string): Promise<string> {
  return mkdtemp(path.join(os.tmpdir(), `shadowclone-${prefix}-`));
}

test("forget leaves a directory the manifest names that is not a repository", async () => {
  const homeDirectory = await scratch("forget-tampered-home");
  const paths = createProjectPaths({ homeDirectory, platform: "darwin" });
  const unrelated = await scratch("unrelated");

  await mkdir(path.join(unrelated, ".claude", "agents"), { recursive: true });

  const victim = path.join(unrelated, ".claude", "agents", "shadowclone.md");

  await writeFile(victim, "someone else's file");

  await writeInstallations({
    filePath: paths.installationsFile,
    state: {
      version: 1,
      installations: [
        {
          directory: unrelated,
          artifacts: ["agent"],
          excludes: [".claude/agents/shadowclone.md"],
        },
      ],
    },
  });

  await forgetAll({ paths });

  expect(await Bun.file(victim).exists()).toBeTrue();
  expect(await Bun.file(paths.installationsFile).exists()).toBeFalse();
});

test("forget never follows a symbolic link out of a recorded repository", async () => {
  const homeDirectory = await scratch("forget-symlink-home");
  const paths = createProjectPaths({ homeDirectory, platform: "darwin" });
  const repository = await scratch("forget-symlink-repo");
  const init = Bun.spawn({
    cmd: ["git", "-C", repository, "init"],
    stdout: "ignore",
    stderr: "ignore",
  });

  expect(await init.exited).toBe(0);

  const outside = await scratch("forget-symlink-outside");

  await mkdir(path.join(outside, "agents"), { recursive: true });

  const victim = path.join(outside, "agents", "shadowclone.md");

  await writeFile(victim, "someone else's file");
  await symlink(outside, path.join(repository, ".claude"));

  await writeInstallations({
    filePath: paths.installationsFile,
    state: {
      version: 1,
      installations: [
        {
          directory: repository,
          artifacts: ["agent", "delegation-skill"],
          excludes: [],
        },
      ],
    },
  });

  await forgetAll({ paths });

  expect(await Bun.file(victim).exists()).toBeTrue();
});
