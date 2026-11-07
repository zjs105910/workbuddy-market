import { expect, test } from "bun:test";
import { cp, mkdtemp, realpath } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { publishEnvironmentRevision, readEnvironment } from "@shadowclone/environment";
import { applyBuild } from "./apply";
import { buildInput } from "./testing";
import { previewBuild } from "./plan";
import { renderBuildSkillSync, syncBuildSkills } from "./sync";
import { addedLine, copyPath, installedBuild, newerPackage, skillRoots } from "./syncFixtures";
import { seedSkillsDirectory } from "@shadowclone/core";

test("an unedited installed skill takes the newer bundled version in every copy", async () => {
  const setup = await installedBuild();
  const synced = await syncBuildSkills({
    state: setup.state,
    packagedSkillsDirectory: await newerPackage(),
  });

  await publishEnvironmentRevision({
    paths: setup.paths,
    updates: synced.updates,
    state: synced.state,
  });

  for (const root of skillRoots) {
    expect(await Bun.file(copyPath({ home: setup.home, root })).text()).toEndWith(addedLine);
  }

  expect(synced.updated).toEqual([{ name: "verify-and-review", copies: 3 }]);
  expect(synced.kept).toEqual([]);
  expect(renderBuildSkillSync(synced)).toEqual([
    "Updated verify-and-review to the bundled version (3 copies).",
  ]);
});

test("an edited copy is kept, named, and left out of the update", async () => {
  const setup = await installedBuild();
  const edited = copyPath({ home: setup.home, root: ".claude/skills" });

  await Bun.write(edited, `${await Bun.file(edited).text()}\nMy own rule.\n`);

  const synced = await syncBuildSkills({
    state: setup.state,
    packagedSkillsDirectory: await newerPackage(),
  });

  expect(synced.updates).toEqual([]);
  expect(synced.updated).toEqual([]);
  expect(renderBuildSkillSync(synced)).toEqual([
    `Kept your edited copy of verify-and-review at ${edited}. Review it in shadowclone wizard.`,
  ]);
});

test("a skill edited in the build editor is not replaced by the bundled version", async () => {
  const base = await Bun.file(
    path.join(await seedSkillsDirectory(), "verify-and-review/SKILL.md"),
  ).text();
  const setup = await installedBuild({
    edits: { "verify-and-review": `${base}\nBuild editor rule.\n` },
  });
  const synced = await syncBuildSkills({
    state: setup.state,
    packagedSkillsDirectory: await newerPackage(),
  });

  expect(synced.updates).toEqual([]);
  expect(synced.updated).toEqual([]);
  expect(synced.kept).toEqual([]);
});

test("an edit that a wizard apply copied to every copy is kept at the next sync", async () => {
  const setup = await installedBuild();
  const edited = copyPath({ home: setup.home, root: ".claude/skills" });

  await Bun.write(edited, `${await Bun.file(edited).text()}\nMy own rule.\n`);
  await applyBuild({
    paths: setup.paths,
    cwd: setup.cwd,
    plan: await previewBuild({
      paths: setup.paths,
      cwd: setup.cwd,
      input: buildInput({ choices: { "verify-and-review": true } }),
    }),
  });

  const state = await readEnvironment(setup.paths);

  if (state === null) {
    throw new Error("The build did not record an environment.");
  }

  const synced = await syncBuildSkills({ state, packagedSkillsDirectory: await newerPackage() });

  expect(synced.updates).toEqual([]);
  expect(synced.kept.map((entry) => entry.filePath).sort()).toEqual(
    skillRoots.map((root) => copyPath({ home: setup.home, root })).sort(),
  );
});

test("a release that changes only a script installs it next to every copy", async () => {
  const setup = await installedBuild();
  const packaged = await realpath(await mkdtemp(path.join(os.tmpdir(), "shadowclone-package-")));

  await cp(await seedSkillsDirectory(), packaged, { recursive: true });
  await Bun.write(path.join(packaged, "verify-and-review/scripts/check.mjs"), "export {};\n");

  const synced = await syncBuildSkills({ state: setup.state, packagedSkillsDirectory: packaged });

  await publishEnvironmentRevision({
    paths: setup.paths,
    updates: synced.updates,
    state: synced.state,
  });

  for (const root of skillRoots) {
    expect(
      await Bun.file(path.join(setup.home, root, "verify-and-review/scripts/check.mjs")).text(),
    ).toBe("export {};\n");
  }

  expect(renderBuildSkillSync(synced)).toEqual([
    "Updated verify-and-review to the bundled version (3 copies).",
  ]);
});
