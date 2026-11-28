import { expect, test } from "bun:test";
import { chmod, lstat, mkdtemp, realpath } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import {
  type BuildContext,
  type BuildDefinition,
  emptyEnvironment,
  type EnvironmentState,
  publishEnvironmentRevision,
} from "@shadowclone/environment";
import { buildFixture } from "./testing";
import { publishBuildSkill } from "./publication";
import { retireBuildSkills } from "./retirement";
import type { BuildItem } from "./types";

const skillText = [
  "---",
  "name: fixture-checks",
  "description: Run the fixture check before handoff.",
  "metadata:",
  "  shadowclone-category: review",
  "  shadowclone-section: workflow",
  "  shadowclone-applies-when: before handoff",
  "---",
  "# Fixture checks",
  "",
  "Run `scripts/check.mjs` on the changed files.",
  "",
].join("\n");

const destinations = [".agents/skills", ".claude/skills", ".gemini/config/skills"];

type Packaged = BuildContext & {
  readonly home: string;
  readonly packaged: string;
  readonly build: BuildDefinition;
  readonly item: BuildItem;
};

async function packagedSkill(script: string): Promise<Packaged> {
  const context = await buildFixture();
  const packaged = await realpath(await mkdtemp(path.join(os.tmpdir(), "shadowclone-packaged-")));
  const home = path.dirname(context.paths.shadowcloneDirectory);

  await Bun.write(path.join(packaged, "fixture-checks/SKILL.md"), skillText);
  await writeScript({ packaged, script });

  return {
    ...context,
    home,
    packaged,
    build: { id: "global", scope: "global", directory: home, choices: {}, edits: {}, custom: [] },
    item: {
      id: "fixture-checks",
      name: "fixture-checks",
      title: "Fixture checks",
      description: "Run the fixture check before handoff.",
      text: skillText,
      kind: "skill",
      category: null,
      section: null,
      axis: null,
      alwaysOn: false,
      owner: "packaged",
    },
  };
}

function activeState(setup: Packaged): EnvironmentState {
  return { ...emptyEnvironment, phase: "active", builds: [setup.build] };
}

async function writeScript(options: { readonly packaged: string; readonly script: string }) {
  const filePath = path.join(options.packaged, "fixture-checks/scripts/check.mjs");

  await Bun.write(filePath, options.script);
  await chmod(filePath, 0o755);
}

async function publish(options: { readonly setup: Packaged; readonly state: EnvironmentState }) {
  const published = await publishBuildSkill({
    ...options.setup,
    state: options.state,
    text: skillText,
    edited: false,
    packagedSkillsDirectory: options.setup.packaged,
  });

  await publishEnvironmentRevision({
    paths: options.setup.paths,
    updates: published.updates,
    state: published.state,
  });

  return published.state;
}

function installedScript(options: { readonly setup: Packaged; readonly root: string }) {
  return path.join(options.setup.home, options.root, "fixture-checks/scripts/check.mjs");
}

test("a packaged skill publishes its script next to every installed copy, with its mode", async () => {
  const setup = await packagedSkill('console.log("check v1");\n');
  const state = await publish({ setup, state: activeState(setup) });

  for (const root of destinations) {
    const filePath = installedScript({ setup, root });

    expect(await Bun.file(filePath).text()).toBe('console.log("check v1");\n');
    expect((await lstat(filePath)).mode & 0o777).toBe(0o755);
  }

  expect(state.artifacts.filter((artifact) => artifact.kind === "resource")).toHaveLength(3);
});

test("an unedited script copy takes the new packaged version, and an edited one blocks", async () => {
  const setup = await packagedSkill('console.log("check v1");\n');
  const first = await publish({ setup, state: activeState(setup) });

  await writeScript({ packaged: setup.packaged, script: 'console.log("check v2");\n' });

  const second = await publish({ setup, state: first });

  expect(await Bun.file(installedScript({ setup, root: ".claude/skills" })).text()).toBe(
    'console.log("check v2");\n',
  );

  await Bun.write(installedScript({ setup, root: ".claude/skills" }), 'console.log("mine");\n');
  await writeScript({ packaged: setup.packaged, script: 'console.log("check v3");\n' });

  await expect(publish({ setup, state: second })).rejects.toThrow("Skill resource copies disagree");
});

test("retiring the skill removes unedited scripts and keeps an edited one with a warning", async () => {
  const setup = await packagedSkill('console.log("check v1");\n');
  const state = await publish({ setup, state: activeState(setup) });

  await Bun.write(installedScript({ setup, root: ".agents/skills" }), 'console.log("mine");\n');

  const retired = await retireBuildSkills({ state, build: setup.build, retained: new Set() });

  await publishEnvironmentRevision({ paths: setup.paths, updates: retired.updates, state });

  expect(await Bun.file(installedScript({ setup, root: ".claude/skills" })).exists()).toBeFalse();
  expect(
    await Bun.file(installedScript({ setup, root: ".gemini/config/skills" })).exists(),
  ).toBeFalse();
  expect(await Bun.file(installedScript({ setup, root: ".agents/skills" })).text()).toBe(
    'console.log("mine");\n',
  );
  expect(retired.warnings).toEqual([
    "Preserved an externally edited copy of fixture-checks; it remains discoverable by its harness.",
  ]);
});

test("a packaged skill that names a missing script does not publish", async () => {
  const setup = await packagedSkill('console.log("check v1");\n');

  await expect(
    publishBuildSkill({
      ...setup,
      state: activeState(setup),
      text: skillText.replace("scripts/check.mjs", "scripts/missing.mjs"),
      edited: false,
      packagedSkillsDirectory: setup.packaged,
    }),
  ).rejects.toThrow();
});
