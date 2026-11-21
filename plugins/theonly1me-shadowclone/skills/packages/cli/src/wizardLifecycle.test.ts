import { expect, test } from "bun:test";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { createProjectPaths } from "@shadowclone/core";
import { loadSeedLibrary } from "@shadowclone/skills";
import { runWizard } from "./wizard";
import { wizardAnswers } from "./wizardFixtures";

async function runChoices(options: {
  readonly paths: ReturnType<typeof createProjectPaths>;
  readonly skill: string;
}): Promise<void> {
  const library = await loadSeedLibrary();
  const answers = [...wizardAnswers({ library, skill: options.skill })];

  await runWizard({
    paths: options.paths,
    library,
    answer: () => answers.shift() ?? null,
    confirm: () => true,
    writeLine: () => {},
  });
}

function skillPath(options: {
  readonly home: string;
  readonly provider: ".agents" | ".claude";
  readonly name: string;
}): string {
  return path.join(options.home, options.provider, "skills", options.name, "SKILL.md");
}

const firstSkill = "tests-that-catch-bugs";
const secondSkill = "verify-and-review";

test("removes an unedited starter skill when another skill replaces it", async () => {
  const home = await mkdtemp(path.join(os.tmpdir(), "shadowclone-wizard-life-"));
  const paths = createProjectPaths({ homeDirectory: home, platform: "darwin" });

  await runChoices({ paths, skill: firstSkill });
  await runChoices({ paths, skill: secondSkill });

  expect(
    await Bun.file(skillPath({ home, provider: ".agents", name: firstSkill })).exists(),
  ).toBeFalse();
  expect(
    await Bun.file(skillPath({ home, provider: ".agents", name: secondSkill })).exists(),
  ).toBeTrue();
});

test("repairs a missing copy of a selected portable skill", async () => {
  const home = await mkdtemp(path.join(os.tmpdir(), "shadowclone-wizard-life-"));
  const paths = createProjectPaths({ homeDirectory: home, platform: "darwin" });

  await runChoices({ paths, skill: firstSkill });

  const claudeSkill = skillPath({
    home,
    provider: ".claude",
    name: firstSkill,
  });

  await rm(path.dirname(claudeSkill), { recursive: true, force: true });

  await runChoices({ paths, skill: firstSkill });

  expect(await Bun.file(claudeSkill).exists()).toBeTrue();
});

test("preserves an edited starter skill when another skill replaces it", async () => {
  const home = await mkdtemp(path.join(os.tmpdir(), "shadowclone-wizard-life-"));
  const paths = createProjectPaths({ homeDirectory: home, platform: "darwin" });

  await runChoices({ paths, skill: firstSkill });

  const editedSkill = skillPath({
    home,
    provider: ".agents",
    name: firstSkill,
  });
  const editedBody = "Keep the reasoning in names and tests.";

  await Bun.write(editedSkill, `${await Bun.file(editedSkill).text()}\n${editedBody}\n`);

  await runChoices({ paths, skill: secondSkill });

  expect(await Bun.file(editedSkill).text()).toContain(editedBody);
  expect(
    await Bun.file(skillPath({ home, provider: ".agents", name: secondSkill })).exists(),
  ).toBeTrue();
});
