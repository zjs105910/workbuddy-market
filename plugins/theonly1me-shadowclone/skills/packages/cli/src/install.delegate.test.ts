import { expect, test } from "bun:test";
import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { defaultConfig, writeConfig, canonicalPath, createProjectPaths } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";
import { installLiveClone } from "./install";
import { readInstallations } from "@shadowclone/environment";

async function repository(): Promise<{
  readonly targetDirectory: string;
  readonly paths: ProjectPaths;
}> {
  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-delegate-home-"),
  );
  const targetDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-delegate-repo-"),
  );
  const init = Bun.spawn({
    cmd: ["git", "-C", targetDirectory, "init"],
    stdout: "ignore",
    stderr: "ignore",
  });

  expect(await init.exited).toBe(0);

  const paths = createProjectPaths({ homeDirectory, platform: "darwin" });

  await writeConfig({ config: defaultConfig, configPath: paths.configFile });

  return { targetDirectory, paths };
}

const skillRelativePath = path.join(
  ".claude",
  "skills",
  "shadowclone",
  "SKILL.md",
);

test("the delegation skill is absent unless it is asked for", async () => {
  const { targetDirectory, paths } = await repository();

  await installLiveClone({
    cwd: targetDirectory,
    configPath: paths.configFile,
    paths,
    managedConfigPath: null,
  });

  expect(
    await Bun.file(path.join(targetDirectory, skillRelativePath)).exists(),
  ).toBeFalse();

  const excludes = await Bun.file(
    path.join(targetDirectory, ".git", "info", "exclude"),
  ).text();

  expect(excludes).toContain(".claude/agents/shadowclone.md");
  expect(excludes).not.toContain(".claude/skills/shadowclone/");

  const state = await readInstallations(paths.installationsFile);

  expect(state.installations).toHaveLength(1);
  expect(state.installations[0]?.artifacts).toEqual(["agent"]);
  expect(state.installations[0]?.directory).toBe(
    canonicalPath(targetDirectory),
  );
});

test("the delegation skill briefs the clone instead of forwarding the request", async () => {
  const { targetDirectory, paths } = await repository();

  await installLiveClone({
    cwd: targetDirectory,
    configPath: paths.configFile,
    paths,
    managedConfigPath: null,
    autoDelegate: true,
  });

  const skill = await Bun.file(
    path.join(targetDirectory, skillRelativePath),
  ).text();

  expect(skill).toContain("name: shadowclone");
  expect(skill).toContain("**Objective.**");
  expect(skill).toContain("**Validation.**");
  expect(skill).toContain("Never forward the user's message verbatim.");
  expect(skill).not.toContain("verbatim in the tool prompt");

  const state = await readInstallations(paths.installationsFile);

  expect(state.installations[0]?.artifacts).toEqual([
    "agent",
    "delegation-skill",
  ]);
});

test("reinstalling without the flag keeps ownership of an earlier skill", async () => {
  const { targetDirectory, paths } = await repository();
  const install = (autoDelegate: boolean) =>
    installLiveClone({
      cwd: targetDirectory,
      configPath: paths.configFile,
      paths,
      managedConfigPath: null,
      autoDelegate,
    });

  await install(true);
  await install(false);

  const state = await readInstallations(paths.installationsFile);

  expect(state.installations).toHaveLength(1);
  expect(state.installations[0]?.artifacts).toEqual([
    "agent",
    "delegation-skill",
  ]);
});
