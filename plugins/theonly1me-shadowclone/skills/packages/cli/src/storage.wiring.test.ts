import { expect, test } from "bun:test";
import { chmod, mkdir, mkdtemp, stat, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { defaultConfig, writeConfig, createProjectPaths } from "@shadowclone/core";
import { openEventIndex } from "@shadowclone/sessions";
import { profileRulePath, type ProfileRule } from "@shadowclone/profile";
import { doctor } from "./doctor";
import { writeProfile } from "@shadowclone/environment";

async function scratchPaths(): Promise<ReturnType<typeof createProjectPaths>> {
  const home = await mkdtemp(path.join(os.tmpdir(), "shadowclone-wiring-"));

  return createProjectPaths({
    homeDirectory: home,
    platform: process.platform,
  });
}

async function modeOf(target: string): Promise<number> {
  return (await stat(target)).mode & 0o777;
}

test("the config write leaves an owner-only file", async () => {
  const paths = await scratchPaths();

  await writeConfig({ config: defaultConfig, configPath: paths.configFile });

  expect(await modeOf(paths.configFile)).toBe(0o600);
  expect(await modeOf(paths.shadowcloneDirectory)).toBe(0o700);
});

test("the profile write leaves owner-only rule files and state", async () => {
  const paths = await scratchPaths();

  const rule: ProfileRule = {
    key: "rule-one",
    title: "Runs focused checks",
    body: "Run the narrow check before the full suite.",
    section: "workflow",
    scope: "org",
    originDirectory: "github.com--acme--936913df4a5c268b",
    repositoryName: null,
    source: "mined",
    status: "active",
    proposal: null,
    appliesWhen: [],
    evidence: { for: ["event:one"], against: [] },
    observations: 2,
    lastSeen: "2026-09-05",
    sessions: 2,
    origins: ["github.com/acme"],
    importReference: null,
  };

  await writeProfile({ paths, rules: [rule] });

  expect(await modeOf(paths.profileDirectory)).toBe(0o700);
  expect(await modeOf(paths.profileManifestFile)).toBe(0o600);

  const ruleFile = path.join(paths.profileDirectory, profileRulePath(rule));

  expect(await modeOf(ruleFile)).toBe(0o600);
  expect(await modeOf(path.dirname(ruleFile))).toBe(0o700);
});

test("the index database is owner-only", async () => {
  const paths = await scratchPaths();

  const index = await openEventIndex(paths.indexDatabase);

  index.close();

  expect(await modeOf(paths.indexDatabase)).toBe(0o600);
  expect(await modeOf(path.dirname(paths.indexDatabase))).toBe(0o700);
});

test("doctor tightens an installation an older version left loose", async () => {
  const paths = await scratchPaths();

  await mkdir(path.join(paths.shadowcloneDirectory, "runs"), {
    recursive: true,
  });
  await writeFile(path.join(paths.shadowcloneDirectory, "config.toml"), "");
  await chmod(paths.shadowcloneDirectory, 0o755);
  await chmod(path.join(paths.shadowcloneDirectory, "runs"), 0o755);
  await chmod(path.join(paths.shadowcloneDirectory, "config.toml"), 0o644);

  await doctor({
    managedConfigPath: null,
    databasePath: paths.indexDatabase,
    shadowcloneDirectory: paths.shadowcloneDirectory,
    probe: async () => false,
  });

  expect(await modeOf(paths.shadowcloneDirectory)).toBe(0o700);
  expect(await modeOf(path.join(paths.shadowcloneDirectory, "runs"))).toBe(
    0o700,
  );
  expect(
    await modeOf(path.join(paths.shadowcloneDirectory, "config.toml")),
  ).toBe(0o600);
});
