import { expect, test } from "bun:test";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { createProjectPaths } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";
import {
  parseProfileRules,
  readGeneratedProfileState,
  readProfileRejections,
} from "@shadowclone/profile";
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

test("keeps exact reruns byte stable and updates source under one key", async () => {
  const { repository, paths } = await context();
  const sourcePath = path.join(repository, "AGENTS.md");

  await Bun.write(sourcePath, "# Review\n\nReview the focused diff.");
  await importLocal({ paths, repository });

  const first = await currentRule(paths);
  const firstProfile = await Bun.file(first.profilePath).text();
  const firstState = await Bun.file(paths.profileManifestFile).text();

  await importLocal({ paths, repository });

  expect(await Bun.file(first.profilePath).text()).toBe(firstProfile);
  expect(await Bun.file(paths.profileManifestFile).text()).toBe(firstState);

  await Bun.write(sourcePath, "# Review\n\nReview every changed branch.");
  await importLocal({ paths, repository });

  const updated = await currentRule(paths);

  expect(updated.rule.key).toBe(first.rule.key);
  expect(updated.rule.body).toContain("Review every changed branch.");
});

test("preserves profile edits while continuing to track the import", async () => {
  const { repository, paths } = await context();
  const sourcePath = path.join(repository, "CLAUDE.md");

  await Bun.write(sourcePath, "Keep the original guidance.");
  await importLocal({ paths, repository });

  const first = await currentRule(paths);
  const edited = (await Bun.file(first.profilePath).text()).replace(
    "Keep the original guidance.",
    "Keep the user's edited guidance.",
  );

  await Bun.write(first.profilePath, edited);
  await Bun.write(sourcePath, "Replace the generated guidance.");

  const result = await importRepositoryGuidance({
    paths,
    workingDirectory: repository,
    gitMetadataEnabled: false,
  });

  expect(result.imported).toBe(0);
  expect(result.preserved).toBe(1);
  expect(await Bun.file(first.profilePath).text()).toBe(edited);

  const [entry] = await readGeneratedProfileState(paths.profileManifestFile);

  expect(entry?.key).toBe(first.rule.key);
  expect(entry?.importReference).not.toBeNull();
});

test("does not retire an edited import when its source is removed", async () => {
  const { repository, paths } = await context();
  const sourcePath = path.join(repository, "CLAUDE.md");

  await Bun.write(sourcePath, "Keep the original guidance.");
  await importLocal({ paths, repository });

  const first = await currentRule(paths);
  const edited = (await Bun.file(first.profilePath).text()).replace(
    "Keep the original guidance.",
    "Keep the user's guidance after source removal.",
  );

  await Bun.write(first.profilePath, edited);
  await importLocal({ paths, repository });
  await rm(sourcePath);

  const result = await importRepositoryGuidance({
    paths,
    workingDirectory: repository,
    gitMetadataEnabled: false,
  });

  expect(result.retired).toBe(0);
  expect(await Bun.file(first.profilePath).text()).toBe(edited);
});

test("keeps deleted imported guidance rejected", async () => {
  const { repository, paths } = await context();
  const sourcePath = path.join(repository, ".cursorrules");

  await Bun.write(sourcePath, "Keep boundaries explicit.");
  await importLocal({ paths, repository });

  const first = await currentRule(paths);

  await rm(first.profilePath);

  await importLocal({ paths, repository });
  await Bun.write(sourcePath, "Change the source after rejection.");

  const result = await importRepositoryGuidance({
    paths,
    workingDirectory: repository,
    gitMetadataEnabled: false,
  });

  expect(result.rejected).toBe(1);
  expect(await Bun.file(first.profilePath).exists()).toBeFalse();

  const rejections = await readProfileRejections(paths.rejectedProfileFile);

  expect(rejections.map((entry) => entry.key)).toEqual([first.rule.key]);
});

test("retires an unedited import when its source is removed", async () => {
  const { repository, paths } = await context();
  const sourcePath = path.join(repository, "CLAUDE.md");

  await Bun.write(sourcePath, "Keep changes reversible.");
  await importLocal({ paths, repository });

  const first = await currentRule(paths);

  await rm(sourcePath);

  const result = await importRepositoryGuidance({
    paths,
    workingDirectory: repository,
    gitMetadataEnabled: false,
  });

  expect(result.retired).toBe(1);
  expect(await Bun.file(first.profilePath).exists()).toBeFalse();

  const state = await readGeneratedProfileState(paths.profileManifestFile);

  expect(state[0]?.disposition).toBe("retired");
});
