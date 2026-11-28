import { expect, test } from "bun:test";
import { symlink } from "node:fs/promises";
import path from "node:path";
import { defaultConfig, writeConfig } from "@shadowclone/core";
import { skillExecution, skillFixture } from "@shadowclone/environment/testing";
import { inspectSkillLibrary } from "./lifecycle";
import { readMaintenanceState } from "@shadowclone/skills";
import { updateSkillLibrary } from "./update";
import { fixtureSkill } from "@shadowclone/skills/testing";

test("disabled consent prevents library reads and model calls", async () => {
  const setup = await skillFixture();

  await writeConfig({
    configPath: setup.paths.configFile,
    config: defaultConfig,
  });

  const execution = skillExecution();

  await expect(inspectSkillLibrary(setup)).rejects.toThrow("disabled");

  expect(await updateSkillLibrary({ ...setup, execution })).toMatchObject({
    assessed: 0,
  });
  expect(execution.callsUsed()).toBe(0);
});

test("malformed skills and unavailable references are reported without mutation", async () => {
  const setup = await skillFixture();

  await Bun.write(
    setup.filePath,
    `${setup.original}\nRead [guidance](references/missing.md).\n`,
  );
  await Bun.write(
    path.join(setup.home, ".agents/skills/broken/SKILL.md"),
    "Missing metadata",
  );

  expect(await inspectSkillLibrary(setup)).toMatchObject({
    invalid: 2,
    skills: [],
  });
  expect(await Bun.file(setup.filePath).text()).toContain(
    "references/missing.md",
  );
});

test("a skill that names another skill's file in backticks stays valid", async () => {
  const setup = await skillFixture();

  await Bun.write(
    setup.filePath,
    `${setup.original}\nThe review skill keeps its tone in \`references/voice.md\`.\n`,
  );

  expect(await inspectSkillLibrary(setup)).toMatchObject({ invalid: 0 });
});

test("symlinked content is ignored and identical portable copies collapse", async () => {
  const setup = await skillFixture();

  await symlink(
    setup.directory,
    path.join(setup.home, ".claude/skills/linked"),
  );
  await Bun.write(
    path.join(setup.home, ".agents/skills/typed-changes/SKILL.md"),
    fixtureSkill(),
  );

  const discovered = await inspectSkillLibrary(setup);

  expect(discovered.skills).toHaveLength(1);
  expect(discovered.duplicates).toBe(0);
});

test("technical verification findings remain inspectable without rewriting instructions", async () => {
  const setup = await skillFixture();

  expect(
    await updateSkillLibrary({
      ...setup,
      execution: skillExecution({ verify: true }),
    }),
  ).toMatchObject({ verification: 1, applied: 0, pending: 0 });

  const state = await readMaintenanceState(setup.paths);

  expect(Object.values(state.findings)[0]).toContain("needs-verification");
  expect(await Bun.file(setup.filePath).text()).toBe(setup.original);
});
