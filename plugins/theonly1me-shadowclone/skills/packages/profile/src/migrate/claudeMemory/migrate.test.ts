import { expect, test } from "bun:test";
import path from "node:path";
import { defaultConfig, writeConfig } from "@shadowclone/core";
import { migrateClaudeMemory } from "./migrate";
import { claudeMemoryFixture } from "./testFixture";

const remote = "git@github.com:acme/sample-app.git";

test("preview requires feedback review and writes nothing", async () => {
  const setup = await claudeMemoryFixture();

  const result = await migrateClaudeMemory({
    paths: setup.paths,
    cwd: setup.repositoryRoot,
    repositoryRoot: setup.repositoryRoot,
    apply: false,
    managedConfigPath: null,
    readRemote: async () => remote,
    now: 1_789_689_600_000,
  });

  expect(result.plan.reviewRequired).toEqual(["feedback_prefer_bun.md"]);
  expect(
    result.plan.manifest.files.map((file) => [file.kind, file.disposition]),
  ).toContainEqual(["reference", "reference"]);
  expect(
    result.plan.manifest.files.map((file) => [file.kind, file.disposition]),
  ).toContainEqual(["project", "recall-reference"]);
  expect(await Bun.file(result.plan.manifestPath).exists()).toBeFalse();
  expect(
    await Bun.file(
      path.join(setup.directory, "feedback_prefer_bun.md"),
    ).exists(),
  ).toBeTrue();
});

test("apply creates one revision and exact reruns are idempotent", async () => {
  const setup = await claudeMemoryFixture();

  const applied = await migrateClaudeMemory({
    paths: setup.paths,
    cwd: setup.repositoryRoot,
    repositoryRoot: setup.repositoryRoot,
    apply: true,
    decisions: setup.decisions,
    managedConfigPath: null,
    readRemote: async () => remote,
    now: 1_789_689_600_000,
  });

  expect(applied.revisionId).not.toBeNull();
  expect(await Bun.file(applied.plan.manifestPath).exists()).toBeTrue();

  const destinations = applied.plan.manifest.files.flatMap((file) =>
    file.destination === undefined ? [] : [file.destination],
  );

  for (const destination of destinations) {
    expect(
      await Bun.file(
        path.join(setup.paths.profileDirectory, destination),
      ).exists(),
    ).toBeTrue();
  }

  const repeated = await migrateClaudeMemory({
    paths: setup.paths,
    cwd: setup.repositoryRoot,
    repositoryRoot: setup.repositoryRoot,
    apply: true,
    decisions: setup.decisions,
    managedConfigPath: null,
    readRemote: async () => remote,
    now: 1_789_689_600_000,
  });

  expect(repeated.plan.alreadyApplied).toBeTrue();
  expect(repeated.revisionId).toBeNull();
});

test("migration checks consent before inspecting the source", async () => {
  const setup = await claudeMemoryFixture();

  await writeConfig({
    configPath: setup.paths.configFile,
    config: defaultConfig,
  });
  await Bun.write(
    path.join(setup.directory, "unsupported.txt"),
    "must remain unread",
  );
  await expect(
    migrateClaudeMemory({
      paths: setup.paths,
      cwd: setup.repositoryRoot,
      repositoryRoot: setup.repositoryRoot,
      apply: false,
      managedConfigPath: null,
    }),
  ).rejects.toThrow("Enable the claude-memory source");
});

test("a changed source conflicts with its applied manifest", async () => {
  const setup = await claudeMemoryFixture();

  await migrateClaudeMemory({
    paths: setup.paths,
    cwd: setup.repositoryRoot,
    repositoryRoot: setup.repositoryRoot,
    apply: true,
    decisions: setup.decisions,
    managedConfigPath: null,
    readRemote: async () => remote,
  });
  await Bun.write(
    path.join(setup.directory, "reference_queue.md"),
    "---\nname: reference_queue\ndescription: changed\n---\n\nChanged.\n",
  );
  await expect(
    migrateClaudeMemory({
      paths: setup.paths,
      cwd: setup.repositoryRoot,
      repositoryRoot: setup.repositoryRoot,
      apply: false,
      decisions: setup.decisions,
      managedConfigPath: null,
      readRemote: async () => remote,
    }),
  ).rejects.toThrow("changed after migration");
});
