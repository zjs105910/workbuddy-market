import { expect, test } from "bun:test";
import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { defaultConfig, writeConfig, canonicalPath, createProjectPaths } from "@shadowclone/core";
import { skillExecution } from "@shadowclone/environment/testing";
import { installSeedSkills, loadSeedLibrary } from "@shadowclone/skills";
import { updateSkillLibrary } from "./skillMaintenance/update";

test("starter skills wait for review instead of amending automatically", async () => {
  const home = canonicalPath(
    await mkdtemp(path.join(os.tmpdir(), "shadowclone-starter-")),
  );
  const paths = createProjectPaths({ homeDirectory: home, platform: "darwin" });

  await writeConfig({
    configPath: paths.configFile,
    config: {
      ...defaultConfig,
      sources: { ...defaultConfig.sources, "skill-library": true },
      distillation: { deep: true, automatic: false },
    },
  });
  await Bun.write(
    path.join(paths.profileDirectory, "global/engineering.md"),
    "## Naming\n\nUse complete names.\n",
  );

  const library = await loadSeedLibrary();
  const [starter] = library.skills;

  if (!starter) {
    throw new Error("Expected a starter skill");
  }

  await installSeedSkills({
    paths,
    skills: [starter],
    availableSkills: library.skills,
  });

  const skillPath = path.join(home, ".agents/skills", starter.id, "SKILL.md");
  const installed = await Bun.file(skillPath).text();

  expect(
    await updateSkillLibrary({
      paths,
      execution: skillExecution(),
      managedConfigPath: null,
    }),
  ).toMatchObject({ applied: 0, pending: 1 });
  expect(await Bun.file(skillPath).text()).toBe(installed);
});
