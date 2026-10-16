import { expect, test } from "bun:test";
import path from "node:path";
import { environmentCompilation, readEnvironment, undoRevision } from "@shadowclone/environment";
import { applyBuild } from "./apply";
import { previewBuild } from "./plan";
import { buildFixture, buildInput } from "./testing";

test("preview is read-only and applying publishes preferences immediately", async () => {
  const context = await buildFixture();
  const plan = await previewBuild({ ...context, input: buildInput() });

  expect(await readEnvironment(context.paths)).toBeNull();

  const revision = await applyBuild({ ...context, plan });
  const homeDirectory = path.dirname(context.paths.shadowcloneDirectory);
  const preferencePath = path.join(
    homeDirectory,
    ".agents/skills/shadowclone-build-preferences/SKILL.md",
  );
  const content = await Bun.file(preferencePath).text();

  expect(content).toContain("plan");
  expect(revision).not.toBeNull();

  const compilation = await environmentCompilation({
    ...context,
    originDirectory: null,
    repositoryName: null,
  });

  expect(compilation?.markdown).toContain("shadowclone-build-preferences skill");
  expect(compilation?.markdown).toContain(
    "- when adding, changing, or proving a test: tests-that-catch-bugs\n",
  );
  expect(compilation?.markdown).not.toContain(homeDirectory);
  expect(
    (await previewBuild({ ...context, input: buildInput() })).updates,
  ).toHaveLength(0);
});

test("undo restores an applied build and its native integrations", async () => {
  const context = await buildFixture();
  const plan = await previewBuild({ ...context, input: buildInput() });
  const id = await applyBuild({ ...context, plan });

  if (id === null) {
    throw new Error("Expected an applied revision");
  }

  await undoRevision({ paths: context.paths, id });

  expect(await readEnvironment(context.paths)).toBeNull();
  expect(
    await Bun.file(
      path.join(
        path.dirname(context.paths.shadowcloneDirectory),
        ".claude/skills/tests-that-catch-bugs/SKILL.md",
      ),
    ).exists(),
  ).toBeFalse();
});

test("an intervening skill edit invalidates the preview without partial writes", async () => {
  const context = await buildFixture();
  const initial = await previewBuild({ ...context, input: buildInput() });

  await applyBuild({ ...context, plan: initial });

  const next = await previewBuild({
    ...context,
    input: buildInput({ choices: { "tests-that-catch-bugs": false } }),
  });
  const skillPath = path.join(
    path.dirname(context.paths.shadowcloneDirectory),
    ".agents/skills/tests-that-catch-bugs/SKILL.md",
  );
  const edited = `${await Bun.file(skillPath).text()}\nPreserve this edit.\n`;

  await Bun.write(skillPath, edited);

  await expect(applyBuild({ ...context, plan: next })).rejects.toThrow(
    "conflicts",
  );

  expect(await Bun.file(skillPath).text()).toBe(edited);
});

test("a deselected skill that left the library does not block the build, and a selected one does", async () => {
  const context = await buildFixture();

  expect(
    (
      await previewBuild({
        ...context,
        input: buildInput({ choices: { "retired-skill": false, "verify-and-review": true } }),
      })
    ).input.choices,
  ).toEqual({
    "retired-skill": false,
    "verify-and-review": true,
    "write-plain-english": true,
  });
  await expect(
    previewBuild({ ...context, input: buildInput({ choices: { "retired-skill": true } }) }),
  ).rejects.toThrow("The selected library changed; reload the build before applying");
});
