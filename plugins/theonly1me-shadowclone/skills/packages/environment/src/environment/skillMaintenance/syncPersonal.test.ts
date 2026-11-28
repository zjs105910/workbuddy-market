import { expect, test } from "bun:test";
import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { createProjectPaths } from "@shadowclone/core";
import { configureSkillMaintenance, syncPersonalSkills } from "@shadowclone/skills";
import { fixtureSkill } from "@shadowclone/skills/testing";

test("personal skill sync preserves conflicting user copies for review", async () => {
  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-skill-sync-"),
  );
  const paths = createProjectPaths({ homeDirectory, platform: "darwin" });
  const claudeSkill = path.join(
    homeDirectory,
    ".claude/skills/typed-changes/SKILL.md",
  );
  const agentSkill = path.join(
    homeDirectory,
    ".agents/skills/typed-changes/SKILL.md",
  );
  const original = fixtureSkill();
  const edited = `${original}\nKeep the user-owned copy.\n`;

  await Bun.write(claudeSkill, original);
  await Bun.write(agentSkill, edited);
  await configureSkillMaintenance({
    scope: "global",
    paths,
    cwd: homeDirectory,
    managedConfigPath: null,
  });

  const result = await syncPersonalSkills({ paths });

  expect(result.conflicts).toBeGreaterThan(0);
  expect(await Bun.file(claudeSkill).text()).toBe(original);
  expect(await Bun.file(agentSkill).text()).toBe(edited);
  expect(
    await Bun.file(
      path.join(homeDirectory, ".codex/skills/typed-changes/SKILL.md"),
    ).exists(),
  ).toBeFalse();
});
