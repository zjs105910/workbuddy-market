import { expect, test } from "bun:test";
import path from "node:path";
import {
  type EnvironmentArtifact,
  environmentFile,
  publishEnvironmentRevision,
  renderEnvironment,
} from "@shadowclone/environment";
import { fingerprint, seedSkillsDirectory } from "@shadowclone/core";
import { parseSkillDocument, loadSeedLibrary } from "@shadowclone/skills";
import { renderRetiredSkillChanges } from "./retired";
import { migrateRetiredSkills } from "./retiredMigration";
import { installedBuild, skillRoots } from "./syncFixtures";

const shippedText = (name: string) =>
  Bun.file(path.join(import.meta.dir, `fixtures/${name}-0.0.17.md`)).text();

async function olderInstall(options: {
  readonly retired: Readonly<Record<string, boolean>>;
  readonly edits?: Readonly<Record<string, string>>;
  readonly before?: (home: string) => Promise<void>;
}) {
  const setup = await installedBuild({ choices: { "verify-and-review": true } });
  const artifacts: EnvironmentArtifact[] = [];

  for (const [name, selected] of Object.entries(options.retired)) {
    const text = await shippedText(name);

    for (const root of selected ? skillRoots : []) {
      const filePath = path.join(setup.home, root, name, "SKILL.md");

      await Bun.write(filePath, text);
      artifacts.push({
        filePath,
        original: null,
        fingerprint: fingerprint(text),
        kind: "skill",
        scope: "global",
        name,
        description: parseSkillDocument(text).metadata.description,
        learningKeys: [],
        buildId: "global",
        buildEntryId: name,
      });
    }
  }

  const state = {
    ...setup.state,
    builds: setup.state.builds.map((build) => ({
      ...build,
      choices: { ...build.choices, ...options.retired },
      edits: { ...build.edits, ...options.edits },
    })),
    artifacts: [...setup.state.artifacts, ...artifacts],
  };

  await Bun.write(environmentFile(setup.paths), renderEnvironment(state));
  await options.before?.(setup.home);

  return { ...setup, state };
}

async function migratedInstall(options: Parameters<typeof olderInstall>[0]) {
  const setup = await olderInstall(options);
  const result = await migrateRetiredSkills({ paths: setup.paths, state: setup.state });

  await publishEnvironmentRevision({
    paths: setup.paths,
    updates: result.updates,
    state: result.state,
  });

  const installed = async (name: string) =>
    Promise.all(
      skillRoots.map((root) => Bun.file(path.join(setup.home, root, name, "SKILL.md")).exists()),
    );

  return { ...setup, result, installed };
}

test("retired skills are replaced in the build, and their copies go away", async () => {
  const setup = await migratedInstall({
    retired: { "testing-first": true, "prove-regression-tests": true },
  });

  expect(setup.result.state.builds.map((build) => build.choices)).toEqual([
    { "verify-and-review": true, "write-plain-english": true, "tests-that-catch-bugs": true },
  ]);
  expect(await setup.installed("testing-first")).toEqual([false, false, false]);
  expect(await setup.installed("prove-regression-tests")).toEqual([false, false, false]);

  for (const root of skillRoots) {
    expect(
      await Bun.file(path.join(setup.home, root, "tests-that-catch-bugs/SKILL.md")).text(),
    ).toBe(
      await Bun.file(
        path.join(await seedSkillsDirectory(), "tests-that-catch-bugs/SKILL.md"),
      ).text(),
    );
  }

  expect(renderRetiredSkillChanges(setup.result.changes)).toEqual([
    "Replaced prove-regression-tests and testing-first with tests-that-catch-bugs in your global build.",
    'To keep the testing-first default, run: shadowclone remember --global "Write the failing test before the production change."',
  ]);
});

test("an edited retired copy stays selected, and the other retired skill is still replaced", async () => {
  let edited = "";
  const setup = await migratedInstall({
    retired: { "testing-first": true, "prove-regression-tests": true },
    before: async (home) => {
      edited = path.join(home, ".claude/skills/testing-first/SKILL.md");
      await Bun.write(edited, `${await Bun.file(edited).text()}\nMy own rule.\n`);
    },
  });

  expect(setup.result.state.builds.map((build) => build.choices)).toEqual([
    {
      "verify-and-review": true,
      "write-plain-english": true,
      "testing-first": true,
      "tests-that-catch-bugs": true,
    },
  ]);
  expect(await setup.installed("testing-first")).toEqual([true, true, true]);
  expect(await setup.installed("prove-regression-tests")).toEqual([false, false, false]);
  expect(renderRetiredSkillChanges(setup.result.changes)).toEqual([
    `Kept your edited copy of testing-first at ${edited}. It is no longer bundled. To replace it with tests-that-catch-bugs, use shadowclone wizard.`,
    "Replaced prove-regression-tests with tests-that-catch-bugs in your global build.",
  ]);
});

test("a retired skill changed in the build editor stays selected and is named", async () => {
  const setup = await migratedInstall({
    retired: { "testing-first": true },
    edits: { "testing-first": `${await shippedText("testing-first")}\nBuild editor rule.\n` },
  });

  expect(setup.result.updates).toEqual([]);
  expect(renderRetiredSkillChanges(setup.result.changes)).toEqual([
    "Kept testing-first in your global build, because you changed it in the build editor. It is no longer bundled. To replace it with tests-that-catch-bugs, use shadowclone wizard.",
  ]);
});

test("a deselected retired skill leaves the build without adding its replacement", async () => {
  const setup = await migratedInstall({ retired: { "testing-first": false } });

  expect(setup.result.state.builds.map((build) => build.choices)).toEqual([
    { "verify-and-review": true, "write-plain-english": true },
  ]);
  expect(await setup.installed("tests-that-catch-bugs")).toEqual([false, false, false]);
  expect(setup.result.changes).toEqual([]);
});

test("a replacement that cannot be installed is reported and leaves the build unchanged", async () => {
  const setup = await migratedInstall({
    retired: { "testing-first": true },
    before: async (home) => {
      await Bun.write(
        path.join(home, ".claude/skills/tests-that-catch-bugs/SKILL.md"),
        "---\nname: tests-that-catch-bugs\ndescription: The user's own skill.\n---\n\nMine.\n",
      );
    },
  });

  expect(setup.result.state.builds.map((build) => build.choices)).toEqual([
    { "verify-and-review": true, "write-plain-english": true, "testing-first": true },
  ]);
  expect(await setup.installed("testing-first")).toEqual([true, true, true]);
  expect(renderRetiredSkillChanges(setup.result.changes)).toEqual([
    "Could not replace testing-first with tests-that-catch-bugs in your global build: An existing skill occupies this destination; select that skill to edit it",
  ]);
});

test("nothing migrates while a retired skill is still in the bundled library", async () => {
  const setup = await olderInstall({ retired: { "testing-first": true } });
  const libraryIds = new Set([
    ...(await loadSeedLibrary()).guidance.map((entry) => entry.id),
    "testing-first",
  ]);
  const result = await migrateRetiredSkills({ paths: setup.paths, state: setup.state, libraryIds });

  expect(result.updates).toEqual([]);
  expect(result.changes).toEqual([]);
});
