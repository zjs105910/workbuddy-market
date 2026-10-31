import { expect, test } from "bun:test";
import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { createProjectPaths } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";
import { parseProfileRules, readGeneratedProfileState } from "@shadowclone/profile";
import { importRepositoryGuidance } from "./importRepositoryGuidance";

async function context(): Promise<{
  readonly repository: string;
  readonly paths: ProjectPaths;
}> {
  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-import-state-"),
  );
  const repository = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-import-source-"),
  );

  return {
    repository,
    paths: createProjectPaths({ homeDirectory, platform: "darwin" }),
  };
}

async function currentRule(paths: ProjectPaths) {
  const entries = await readGeneratedProfileState(paths.profileManifestFile);
  const entry = entries.find(
    (candidate) => candidate.disposition === "present",
  );

  if (!entry) {
    throw new Error("Expected a present imported profile entry");
  }

  const profilePath = path.join(paths.profileDirectory, entry.relativePath);
  const [rule] = parseProfileRules(await Bun.file(profilePath).text());

  if (!rule) {
    throw new Error("Expected an imported profile rule");
  }

  return { entry, profilePath, rule };
}

async function importLocal(options: {
  readonly paths: ProjectPaths;
  readonly repository: string;
}): Promise<void> {
  await importRepositoryGuidance({
    ...options,
    workingDirectory: options.repository,
    gitMetadataEnabled: false,
  });
}

test("promotes an isolated import under the same opaque identity", async () => {
  const { repository, paths } = await context();

  await Bun.write(path.join(repository, "AGENTS.md"), "Avoid unsafe paths.");
  await importLocal({ paths, repository });

  const isolated = await currentRule(paths);
  const remote = "git@github.com:acme/platform.git";

  await importRepositoryGuidance({
    paths,
    workingDirectory: repository,
    gitMetadataEnabled: true,
    readRemote: async () => remote,
  });

  const promoted = await currentRule(paths);

  expect(promoted.rule.key).toBe(isolated.rule.key);
  expect(promoted.entry.relativePath).toStartWith(
    "org/github.com--acme--936913df4a5c268b/projects/",
  );
  expect(promoted.entry.relativePath).not.toContain("../");
  expect(await Bun.file(isolated.profilePath).exists()).toBeFalse();

  const state = await Bun.file(paths.profileManifestFile).text();

  expect(state).not.toContain(repository);
  expect(state).not.toContain(remote);
});

test("a remote carrying path traversal stays under its isolated identity", async () => {
  const { repository, paths } = await context();

  await Bun.write(path.join(repository, "AGENTS.md"), "Avoid unsafe paths.");
  await importLocal({ paths, repository });

  const isolated = await currentRule(paths);
  const remote = "git@github.com:acme/../../outside.git";

  await importRepositoryGuidance({
    paths,
    workingDirectory: repository,
    gitMetadataEnabled: true,
    readRemote: async () => remote,
  });

  const current = await currentRule(paths);

  expect(current.entry.relativePath).toBe(isolated.entry.relativePath);
  expect(current.entry.relativePath).toStartWith("org/isolated--");
  expect(current.entry.relativePath).not.toContain("..");

  const state = await Bun.file(paths.profileManifestFile).text();

  expect(state).not.toContain(remote);
});
