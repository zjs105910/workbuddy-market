import { expect, test } from "bun:test";
import { mkdir, mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { createProjectPaths } from "@shadowclone/core";
import { forgetAll } from "./forget";

test("forget all removes only the shadowclone directory", async () => {
  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-forget-"),
  );
  const shadowcloneDirectory = path.join(homeDirectory, ".shadowclone");
  const transcriptDirectory = path.join(homeDirectory, ".claude");

  await mkdir(shadowcloneDirectory);
  await mkdir(transcriptDirectory);
  await Bun.write(path.join(shadowcloneDirectory, "index.db"), "derived");
  await Bun.write(path.join(transcriptDirectory, "session.jsonl"), "source");

  await forgetAll({
    paths: createProjectPaths({ homeDirectory, platform: "darwin" }),
  });

  expect(
    await Bun.file(path.join(shadowcloneDirectory, "index.db")).exists(),
  ).toBeFalse();
  expect(
    await Bun.file(path.join(transcriptDirectory, "session.jsonl")).exists(),
  ).toBeTrue();
});
