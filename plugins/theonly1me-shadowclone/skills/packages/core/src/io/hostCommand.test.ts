import { expect, test } from "bun:test";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { runHostCommand } from "./hostCommand";
import { gitIdentityArguments } from "./gitIdentity";

test("automatic Git ignores hooks and refuses executable repository configuration", async () => {
  const directory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-host-git-"),
  );
  const git = (arguments_: readonly string[]) =>
    runHostCommand({ arguments: ["git", ...arguments_], cwd: directory });

  try {
    expect((await git(["init", "--quiet"])).exitCode).toBe(0);

    await writeFile(path.join(directory, "file"), "fixture");
    await writeFile(
      path.join(directory, ".git", "hooks", "pre-commit"),
      '#!/bin/sh\ntouch "$PWD/escaped"\n',
      { mode: 0o755 },
    );
    await git(["add", "--all"]);

    expect(
      (
        await git([
          "-c",
          "user.name=Fixture",
          "-c",
          "user.email=fixture@example.test",
          "commit",
          "-qm",
          "fixture",
        ])
      ).exitCode,
    ).toBe(0);
    expect(
      await Bun.file(path.join(directory, "escaped")).exists(),
    ).toBeFalse();

    await git(["config", "filter.fixture.clean", "touch escaped"]);
    await expect(git(["add", "--all"])).rejects.toThrow(
      "executable repository configuration",
    );

    expect(
      await Bun.file(path.join(directory, "escaped")).exists(),
    ).toBeFalse();
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("host commits preserve configured identity without carrying other global settings", async () => {
  const directory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-git-identity-"),
  );

  try {
    const home = path.join(directory, "home");

    await mkdir(home);
    await writeFile(
      path.join(home, ".gitconfig"),
      "[user]\nname = Fixture\nemail = fixture@example.test\n[core]\nhooksPath = /untrusted/hooks\n",
    );

    const arguments_ = await gitIdentityArguments({
      cwd: directory,
      environment: {
        PATH: process.env.PATH,
        HOME: home,
        XDG_CONFIG_HOME: home,
      },
    });

    expect(arguments_).toEqual([
      "-c",
      "user.name=Fixture",
      "-c",
      "user.email=fixture@example.test",
    ]);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
