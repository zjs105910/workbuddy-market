import { expect, test } from "bun:test";
import { mkdir, mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { defaultManagedPolicy, readConfig, createProjectPaths } from "@shadowclone/core";
import { readGeneratedProfileState } from "@shadowclone/profile";
import { importRepositoryGuidanceCommand } from "./import";

async function testContext(): Promise<{
  readonly repository: string;
  readonly paths: ReturnType<typeof createProjectPaths>;
}> {
  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-import-home-"),
  );
  const repository = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-import-repo-"),
  );

  return {
    repository,
    paths: createProjectPaths({ homeDirectory, platform: "darwin" }),
  };
}

test("declining import leaves configuration and profile state untouched", async () => {
  const { repository, paths } = await testContext();

  await mkdir(path.join(repository, "CLAUDE.md"));

  const result = await importRepositoryGuidanceCommand({
    paths,
    configPath: paths.configFile,
    workingDirectory: repository,
    managedPolicy: defaultManagedPolicy,
    ask: () => false,
    writeLine: () => {},
  });

  expect(result).toBeNull();
  expect(await Bun.file(paths.configFile).exists()).toBeFalse();
  expect(await Bun.file(paths.profileManifestFile).exists()).toBeFalse();
});

test("persists consent and imports only redacted repository guidance", async () => {
  const { repository, paths } = await testContext();
  const secret = ["sk", "abcdefghijklmnop123456"].join("-");
  const skillPath = path.join(
    repository,
    ".claude",
    "skills",
    "private-review",
    "SKILL.md",
  );

  await mkdir(path.dirname(skillPath), { recursive: true });
  await Bun.write(
    skillPath,
    `---\nname: private-review\n---\n# Review ${secret}\n\nAPI_TOKEN=${secret}`,
  );

  const output: string[] = [];

  const result = await importRepositoryGuidanceCommand({
    paths,
    configPath: paths.configFile,
    workingDirectory: repository,
    managedPolicy: defaultManagedPolicy,
    ask: () => true,
    writeLine: (line) => output.push(line),
  });

  const config = await readConfig({ configPath: paths.configFile });
  const [entry] = await readGeneratedProfileState(paths.profileManifestFile);

  if (!entry) {
    throw new Error("Expected imported profile state");
  }

  const profile = await Bun.file(
    path.join(paths.profileDirectory, entry.relativePath),
  ).text();
  const persisted = `${profile}\n${await Bun.file(paths.profileManifestFile).text()}`;

  expect(result?.imported).toBe(1);
  expect(config.sources["declared-rules"]).toBeTrue();
  expect(persisted).not.toContain(secret);
  expect(persisted).toContain("[redacted:");
  expect(output).toEqual([
    "Imported 1 repository guidance files; 0 preserved; 0 rejected; 0 retired.",
  ]);
  expect(output.join("\n")).not.toContain("SKILL.md");
  expect(output.join("\n")).not.toContain("private-review");
});

test("does not prompt again after repository guidance consent", async () => {
  const { repository, paths } = await testContext();

  await Bun.write(path.join(repository, "AGENTS.md"), "Keep changes focused.");

  let prompts = 0;
  const options = {
    paths,
    configPath: paths.configFile,
    workingDirectory: repository,
    managedPolicy: defaultManagedPolicy,
    ask: () => {
      prompts += 1;

      return true;
    },
    writeLine: () => {},
  };

  await importRepositoryGuidanceCommand(options);
  await importRepositoryGuidanceCommand(options);

  expect(prompts).toBe(1);
});

test("managed policy blocks import before configuration is read", async () => {
  const { repository, paths } = await testContext();
  const policy = {
    ...defaultManagedPolicy,
    allowedSources: defaultManagedPolicy.allowedSources.filter(
      (source) => source !== "declared-rules",
    ),
  };

  await expect(
    importRepositoryGuidanceCommand({
      paths,
      configPath: repository,
      workingDirectory: repository,
      managedPolicy: policy,
      ask: () => true,
      writeLine: () => {},
    }),
  ).rejects.toThrow("Managed policy blocks repository guidance import");
});
