import { expect, test } from "bun:test";
import path from "node:path";
import {
  type BuildContext,
  type BuildInput,
  readEnvironment,
  renderBuildRouting,
} from "@shadowclone/environment";
import { applyBuild } from "./apply";
import { readReleasedShapes, skillName, writeOlderRelease } from "./alwaysOnFixtures";
import { updateBundledSkills } from "./bundledUpdate";
import { buildCatalog } from "./catalog";
import { buildFixture, buildInput } from "./testing";
import { previewBuild } from "./plan";
import { buildDefinition, buildIdentity, selectedItems } from "./selection";

const routingLine = "- before you write any text that a person reads: write-plain-english\n";

async function applyScope(options: {
  readonly context: BuildContext;
  readonly input: Partial<BuildInput>;
}): Promise<void> {
  await applyBuild({
    ...options.context,
    plan: await previewBuild({
      ...options.context,
      input: buildInput({ choices: { "tests-that-catch-bugs": true }, ...options.input }),
    }),
  });
}

async function sharedAndPrivate() {
  const context = await buildFixture();

  await applyScope({ context, input: { scope: "shared" } });
  await applyScope({ context, input: { scope: "private" } });

  const state = await readEnvironment(context.paths);

  if (state === null) {
    throw new Error("The builds did not record an environment.");
  }

  return { context, state };
}

function privateCopy(context: BuildContext): Promise<boolean> {
  return Bun.file(
    path.join(
      context.paths.shadowcloneDirectory,
      "builds",
      buildIdentity({ ...context, scope: "private" }),
      "skills",
      skillName,
      "SKILL.md",
    ),
  ).exists();
}

test("a private build under a shared build leaves the always on skill to the shared build", async () => {
  const { context, state } = await sharedAndPrivate();
  const privateArtifacts = state.artifacts.filter(
    (artifact) =>
      artifact.buildEntryId === skillName &&
      artifact.buildId === buildIdentity({ ...context, scope: "private" }),
  );

  expect(privateArtifacts).toEqual([]);
  expect(await privateCopy(context)).toBeFalse();
  expect(renderBuildRouting({ state, cwd: context.cwd }).split(routingLine)).toHaveLength(2);
});

test("a stored personal choice to turn the always on skill off does not block selection under a shared build", async () => {
  const { context, state } = await sharedAndPrivate();
  const build = buildDefinition({
    ...context,
    input: buildInput({ scope: "private", choices: { [skillName]: false } }),
  });
  const selected = selectedItems({
    state,
    build,
    catalog: await buildCatalog({ ...context, scope: "private" }),
  });

  expect(state.builds.find((entry) => entry.scope === "shared")?.choices[skillName]).toBeTrue();
  expect(selected.map((item) => item.id)).not.toContain(skillName);
  expect(build.choices[skillName]).toBeFalse();
});

test("sync adds the always on skill to a shared build and skips a private build under it", async () => {
  const { context, state } = await sharedAndPrivate();

  await writeOlderRelease({
    paths: context.paths,
    state: { ...state, builds: state.builds.toReversed() },
    directories: [context.cwd],
  });

  const report = await updateBundledSkills(context.paths);
  const persisted = await readReleasedShapes(context.paths);

  expect(report?.alwaysOn.map((change) => [change.kind, change.build.scope])).toEqual([
    ["added", "shared"],
  ]);
  expect(await privateCopy(context)).toBeFalse();
  expect(
    persisted.builds.map((build) => [build.scope, build.choices[skillName]]).toSorted(),
  ).toEqual([
    ["private", undefined],
    ["shared", true],
  ]);
  expect(
    await Bun.file(path.join(context.cwd, ".agents/skills", skillName, "SKILL.md")).exists(),
  ).toBeTrue();
});
