import { expect, test } from "bun:test";
import path from "node:path";
import { writeConfig, defaultConfig } from "@shadowclone/core";
import { rememberPreference } from "../../preferences";
import { configureSkillMaintenance } from "@shadowclone/skills";
import { skillExecution, skillFixture } from "@shadowclone/environment/testing";
import { updateSkillLibrary } from "./update";
import { fixtureSkill } from "@shadowclone/skills/testing";

test("skill contents cross the redaction gate before an assessment prompt", async () => {
  const setup = await skillFixture();
  const secret = `sk-ant-${"A".repeat(90)}`;

  await Bun.write(
    setup.filePath,
    `${setup.original}\nFixture token: ${secret}\n`,
  );

  let prompt = "";
  const execution = skillExecution({
    onPrompt: (text) => {
      prompt = text;
    },
  });

  await updateSkillLibrary({ ...setup, execution });

  expect(execution.callsUsed()).toBe(1);
  expect(prompt).toContain("Fixture token");
  expect(prompt).not.toContain(secret);
  expect(prompt).not.toContain(setup.filePath);
});

test("global skill assessments never receive repository-only preferences", async () => {
  const setup = await skillFixture();

  await rememberPreference({
    ...setup,
    scope: "repository",
    text: "Use the repository-specific migration protocol.",
  });

  let prompt = "";

  await updateSkillLibrary({
    ...setup,
    execution: skillExecution({
      onPrompt: (text) => {
        prompt = text;
      },
    }),
  });

  expect(prompt).not.toContain("repository-specific migration protocol");
});

test("each repository skill root receives only its own scoped guidance", async () => {
  const setup = await skillFixture({ scope: "repository" });
  const other = path.join(setup.home, "other-repository");

  await Bun.write(
    path.join(other, ".claude/skills/typed-changes/SKILL.md"),
    fixtureSkill(),
  );
  await configureSkillMaintenance({
    ...setup,
    cwd: other,
    scope: "repository",
  });
  await rememberPreference({
    ...setup,
    scope: "repository",
    text: "Apply only the first repository protocol.",
  });

  const prompts: string[] = [];

  await updateSkillLibrary({
    ...setup,
    execution: skillExecution({
      onPrompt: (text) => {
        prompts.push(text);
      },
    }),
  });

  expect(prompts).toHaveLength(2);
  expect(
    prompts.filter((prompt) => prompt.includes("first repository protocol")),
  ).toHaveLength(1);
});

test("skill consent never enables transcript capture or deep learning", async () => {
  const setup = await skillFixture();

  await writeConfig({
    configPath: setup.paths.configFile,
    config: defaultConfig,
  });
  await configureSkillMaintenance({ ...setup, scope: "repository" });

  const execution = skillExecution();
  const summary = await updateSkillLibrary({ ...setup, execution });

  expect(execution.callsUsed()).toBe(0);
  expect(summary.assessed).toBe(0);
});
