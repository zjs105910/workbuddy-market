import { mkdtemp, mkdir } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { canonicalPath, createProjectPaths } from "@shadowclone/core";
import type { BuildContext, BuildInput } from "@shadowclone/environment";

export async function buildFixture(): Promise<BuildContext> {
  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-build-"),
  );
  const cwd = path.join(homeDirectory, "sample-repository");

  await mkdir(cwd);

  return {
    paths: createProjectPaths({ homeDirectory, platform: "win32" }),
    cwd: canonicalPath(cwd),
  };
}

export function buildInput(overrides: Partial<BuildInput> = {}): BuildInput {
  return {
    scope: "global",
    choices: { "planning-first": true, "tests-that-catch-bugs": true },
    edits: {},
    custom: [],
    ...overrides,
  };
}
