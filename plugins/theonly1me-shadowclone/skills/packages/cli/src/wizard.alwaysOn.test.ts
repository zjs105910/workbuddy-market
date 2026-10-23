import { expect, test } from "bun:test";
import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { createProjectPaths } from "@shadowclone/core";
import { loadSeedLibrary } from "@shadowclone/skills";
import { runWizard } from "./wizard";
import { wizardAnswers } from "./wizardFixtures";

test("the terminal wizard does not offer write-plain-english, prints it as always included, and installs it", async () => {
  const homeDirectory = await mkdtemp(path.join(os.tmpdir(), "shadowclone-wizard-"));
  const paths = createProjectPaths({ homeDirectory, platform: "darwin" });
  const library = await loadSeedLibrary();
  const answers = [...wizardAnswers({ library, skill: "tests-that-catch-bugs" })];
  const questions: string[] = [];
  const output: string[] = [];

  const result = await runWizard({
    paths,
    library,
    answer: (question) => {
      questions.push(question);

      return answers.shift() ?? null;
    },
    confirm: () => true,
    writeLine: (line) => output.push(line),
  });

  const skillsQuestion = questions.find((question) =>
    question.startsWith("Choose optional skills:"),
  );

  expect(skillsQuestion).toContain("Tests That Catch Bugs");
  expect(skillsQuestion).not.toContain("Write Plain English");
  expect(output).toContain("Always included:");
  expect(output).toContain("  Write Plain English");
  expect(result.selectedGuidanceIds).not.toContain("write-plain-english");
  expect(
    await Bun.file(
      path.join(homeDirectory, ".agents/skills/write-plain-english/SKILL.md"),
    ).exists(),
  ).toBeTrue();
});

test("the terminal wizard installs write-plain-english when the user chooses no optional skills", async () => {
  const homeDirectory = await mkdtemp(path.join(os.tmpdir(), "shadowclone-wizard-"));
  const paths = createProjectPaths({ homeDirectory, platform: "darwin" });
  const library = await loadSeedLibrary();
  const answers = [...library.axes.map(() => "1"), "none"];

  await runWizard({
    paths,
    library,
    answer: () => answers.shift() ?? null,
    confirm: () => true,
    writeLine: () => {},
  });

  expect(
    await Bun.file(
      path.join(homeDirectory, ".agents/skills/write-plain-english/SKILL.md"),
    ).exists(),
  ).toBeTrue();
});
