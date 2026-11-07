import { expect, test } from "bun:test";
import path from "node:path";
import {
  environmentCompilation,
  environmentFile,
  readEnvironment,
  renderEnvironment,
  syncLearningEnvironment,
} from "@shadowclone/environment";
import { applyBuild } from "./apply";
import { skillName, readReleasedShapes, writeOlderRelease } from "./alwaysOnFixtures";
import { updateBundledSkills } from "./bundledUpdate";
import { buildFixture, buildInput } from "./testing";
import { previewBuild } from "./plan";
import { installedBuild, skillRoots } from "./syncFixtures";

const routingLine = "- before you write any text that a person reads: write-plain-english\n";

async function olderGlobalBuild(storedChoice?: false) {
  const setup = await installedBuild();

  await writeOlderRelease({
    paths: setup.paths,
    state: setup.state,
    directories: [setup.home],
    storedChoice,
  });

  return setup;
}

test("sync gives an older build the skill, records it as chosen, and routes it", async () => {
  const setup = await olderGlobalBuild(false);
  const report = await updateBundledSkills(setup.paths);

  expect(report?.alwaysOn).toEqual([
    expect.objectContaining({ kind: "added", skills: [skillName] }),
  ]);

  for (const root of skillRoots) {
    expect(await Bun.file(path.join(setup.home, root, skillName, "SKILL.md")).exists()).toBeTrue();
  }

  expect(await syncLearningEnvironment(setup.paths)).toBeTrue();

  const compilation = await environmentCompilation({
    ...setup,
    originDirectory: null,
    repositoryName: null,
  });
  const persisted = await readReleasedShapes(setup.paths);

  expect(compilation?.markdown).toContain(routingLine);
  expect(persisted.builds.map((build) => build.choices[skillName])).toEqual([true]);
});

test("sync leaves the stored state readable by the released schema", async () => {
  const setup = await olderGlobalBuild();

  await updateBundledSkills(setup.paths);

  const persisted = await readReleasedShapes(setup.paths);

  expect(
    persisted.artifacts.filter((artifact) => artifact.buildEntryId === skillName),
  ).not.toHaveLength(0);
});

test("a second sync adds nothing because the build already has the skill", async () => {
  const setup = await olderGlobalBuild();

  await updateBundledSkills(setup.paths);

  expect((await updateBundledSkills(setup.paths))?.alwaysOn).toEqual([]);
});

test("sync turns the skill on for a build that has it installed but stores it as off", async () => {
  const setup = await installedBuild();

  await Bun.write(
    environmentFile(setup.paths),
    renderEnvironment({
      ...setup.state,
      builds: setup.state.builds.map((build) => ({
        ...build,
        choices: { ...build.choices, [skillName]: false },
      })),
    }),
  );

  const report = await updateBundledSkills(setup.paths);

  expect(report?.alwaysOn).toEqual([expect.objectContaining({ kind: "added" })]);
  expect(
    (await readReleasedShapes(setup.paths)).builds.map((build) => build.choices[skillName]),
  ).toEqual([true]);
});

test("sync reports a skill file that blocks the always on skill and keeps the file", async () => {
  const setup = await olderGlobalBuild();
  const occupied = path.join(setup.home, ".agents/skills", skillName, "SKILL.md");

  await Bun.write(occupied, "My own skill with the same name.\n");

  const report = await updateBundledSkills(setup.paths);

  expect(report?.alwaysOn).toEqual([
    expect.objectContaining({ kind: "failed", skills: [skillName] }),
  ]);
  expect(await Bun.file(occupied).text()).toBe("My own skill with the same name.\n");
});

test("sync gives a shared build the always on skill and its repository routing", async () => {
  const context = await buildFixture();

  await applyBuild({
    ...context,
    plan: await previewBuild({
      ...context,
      input: buildInput({ scope: "shared", choices: { "tests-that-catch-bugs": true } }),
    }),
  });

  const state = await readEnvironment(context.paths);

  if (state === null) {
    throw new Error("The build did not record an environment.");
  }

  await writeOlderRelease({
    paths: context.paths,
    state: {
      ...state,
      artifacts: state.artifacts.filter((artifact) => artifact.kind !== "instructions"),
    },
    directories: [context.cwd],
  });
  await Bun.file(path.join(context.cwd, "AGENTS.md")).delete();
  await Bun.file(path.join(context.cwd, "CLAUDE.md")).delete();
  await updateBundledSkills(context.paths);

  expect(await Bun.file(path.join(context.cwd, "AGENTS.md")).text()).toContain(routingLine);
  expect(
    await Bun.file(path.join(context.cwd, ".agents/skills", skillName, "SKILL.md")).exists(),
  ).toBeTrue();
});
