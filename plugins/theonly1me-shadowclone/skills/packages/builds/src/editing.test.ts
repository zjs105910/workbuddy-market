import { expect, test } from "bun:test";
import path from "node:path";
import { readEnvironment } from "@shadowclone/environment";
import { applyBuild } from "./apply";
import { buildCatalog } from "./catalog";
import { buildFixture, buildInput } from "./testing";
import { previewBuild } from "./plan";

test("a custom skill can be edited, disabled, and equipped again", async () => {
  const context = await buildFixture();

  const input = buildInput({
    custom: [
      {
        name: "measure-first",
        description: "Measure processing changes.",
        body: "Compare before and after measurements.",
      },
    ],
  });

  await applyBuild({
    ...context,
    plan: await previewBuild({ ...context, input }),
  });

  const catalog = await buildCatalog({ ...context, scope: "global" });
  const custom = catalog.find((item) => item.id === "custom:measure-first");

  if (!custom) {
    throw new Error("Missing installed custom skill");
  }

  const edited = {
    ...input,
    edits: { [custom.id]: `${custom.text}\nRepeat each measurement.\n` },
  };

  await applyBuild({
    ...context,
    plan: await previewBuild({ ...context, input: edited }),
  });

  const filePath = path.join(
    path.dirname(context.paths.shadowcloneDirectory),
    ".agents/skills/measure-first/SKILL.md",
  );

  expect(await Bun.file(filePath).text()).toContain("Repeat each measurement.");

  const disabled = {
    ...input,
    choices: { ...input.choices, [custom.id]: false },
  };

  await applyBuild({
    ...context,
    plan: await previewBuild({ ...context, input: disabled }),
  });

  expect(await Bun.file(filePath).exists()).toBeFalse();

  await applyBuild({
    ...context,
    plan: await previewBuild({ ...context, input }),
  });

  expect(await Bun.file(filePath).exists()).toBeTrue();
});

test("reloading an external edit makes it the base for a reviewed change", async () => {
  const context = await buildFixture();
  const input = buildInput();

  await applyBuild({
    ...context,
    plan: await previewBuild({ ...context, input }),
  });

  const filePath = path.join(
    path.dirname(context.paths.shadowcloneDirectory),
    ".agents/skills/tests-that-catch-bugs/SKILL.md",
  );
  const external = `${await Bun.file(filePath).text()}\nKeep the external correction.\n`;

  await Bun.write(filePath, external);

  const catalog = await buildCatalog({ ...context, scope: "global" });
  const current = catalog.find((item) => item.id === "tests-that-catch-bugs");

  expect(current?.text).toBe(external);

  const next = {
    ...input,
    edits: { "tests-that-catch-bugs": `${external}\nAdd a reviewed step.\n` },
  };

  await applyBuild({
    ...context,
    plan: await previewBuild({ ...context, input: next }),
  });

  expect(await Bun.file(filePath).text()).toBe(next.edits["tests-that-catch-bugs"]);
});

test("changed source permissions invalidate a reviewed preview", async () => {
  const context = await buildFixture();
  const plan = await previewBuild({ ...context, input: buildInput() });

  await Bun.write(
    path.join(context.paths.shadowcloneDirectory, "skills.json"),
    "{}",
  );

  await expect(applyBuild({ ...context, plan })).rejects.toThrow(
    "changed after preview",
  );

  expect(await readEnvironment(context.paths)).toBeNull();
});
