import { expect, test } from "bun:test";
import path from "node:path";
import { emptyEnvironment, environmentCompilation } from "@shadowclone/environment";
import { readReleasedShapes } from "./alwaysOnFixtures";
import { applyBuild } from "./apply";
import { buildCatalog } from "./catalog";
import { buildFixture, buildInput } from "./testing";
import { previewBuild } from "./plan";
import { buildDefinition, selectedItems } from "./selection";

const alwaysOnRouting = "- before you write any text that a person reads: write-plain-english\n";

test("a build that turns write-plain-english off still selects it", async () => {
  const context = await buildFixture();
  const catalog = await buildCatalog({ ...context, scope: "global" });
  const build = buildDefinition({
    ...context,
    input: buildInput({ choices: { "write-plain-english": false } }),
  });
  const selected = selectedItems({
    state: { ...emptyEnvironment, phase: "active" },
    build,
    catalog,
  });

  expect(selected.map((item) => item.id)).toEqual(["write-plain-english"]);
});

test("a build with no choices publishes write-plain-english and routes it", async () => {
  const context = await buildFixture();

  await applyBuild({
    ...context,
    plan: await previewBuild({ ...context, input: buildInput({ choices: {} }) }),
  });

  const compilation = await environmentCompilation({
    ...context,
    originDirectory: null,
    repositoryName: null,
  });
  const home = path.dirname(context.paths.shadowcloneDirectory);

  expect(compilation?.markdown).toContain(alwaysOnRouting);
  expect(
    await Bun.file(path.join(home, ".agents/skills/write-plain-english/SKILL.md")).exists(),
  ).toBeTrue();
  expect(
    await Bun.file(
      path.join(home, ".agents/skills/write-plain-english/scripts/check-ste.mjs"),
    ).exists(),
  ).toBeTrue();
});

test("a private build that turns write-plain-english off still routes it", async () => {
  const context = await buildFixture();

  await applyBuild({
    ...context,
    plan: await previewBuild({
      ...context,
      input: buildInput({ scope: "private", choices: { "write-plain-english": false } }),
    }),
  });

  const compilation = await environmentCompilation({
    ...context,
    originDirectory: null,
    repositoryName: null,
  });

  expect(compilation?.markdown).toContain(alwaysOnRouting);
});

test("a shared build writes the always on skill into the repository routing", async () => {
  const context = await buildFixture();

  await applyBuild({
    ...context,
    plan: await previewBuild({
      ...context,
      input: buildInput({ scope: "shared", choices: { "write-plain-english": false } }),
    }),
  });

  expect(await Bun.file(path.join(context.cwd, "AGENTS.md")).text()).toContain(alwaysOnRouting);
  expect(
    await Bun.file(path.join(context.cwd, ".agents/skills/write-plain-english/SKILL.md")).exists(),
  ).toBeTrue();
});

test("a build records write-plain-english as chosen and stores only the released fields", async () => {
  const context = await buildFixture();

  await applyBuild({
    ...context,
    plan: await previewBuild({
      ...context,
      input: buildInput({ choices: { "write-plain-english": false } }),
    }),
  });

  const persisted = await readReleasedShapes(context.paths);

  expect(persisted.builds.map((build) => build.choices["write-plain-english"])).toEqual([true]);
  expect(
    persisted.artifacts.filter((artifact) => artifact.buildEntryId === "write-plain-english"),
  ).not.toHaveLength(0);
});
