import { expect, test } from "bun:test";
import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { createProjectPaths } from "@shadowclone/core";
import { loadSeedLibrary, seedGuidanceProfileKey } from "@shadowclone/skills";
import { wizardAnswers } from "./wizardFixtures";
import {
  parseAxisChoice,
  parseOptionalSkillChoices,
  runWizard,
} from "./wizard";
import { readProfileSnapshot } from "@shadowclone/environment";


test("accepts only displayed axis and optional skill choices", async () => {
  const library = await loadSeedLibrary();
  const [axis] = library.axes;

  if (!axis) {
    throw new Error("The seed library needs an axis");
  }

  for (const response of ["0", "1e0", "comments-none", "Write no"]) {
    expect(parseAxisChoice({ response, guidance: axis.guidance })).toBeNull();
  }

  expect(parseAxisChoice({ response: "1", guidance: axis.guidance })?.id).toBe(
    axis.guidance[0]?.id,
  );

  for (const response of ["0", "1,1", "all,1", "unknown", "Verify"]) {
    expect(
      parseOptionalSkillChoices({
        response,
        skills: library.independentSkills,
      }),
    ).toBeNull();
  }

  expect(
    parseOptionalSkillChoices({
      response: "1, 3",
      skills: library.independentSkills,
    })?.map((skill) => skill.id),
  ).toEqual(
    library.independentSkills
      .filter((_, skillIndex) => skillIndex === 0 || skillIndex === 2)
      .map((skill) => skill.id),
  );
});

test("prints every selection and writes nothing when confirmation is declined", async () => {
  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-wizard-"),
  );
  const paths = createProjectPaths({ homeDirectory, platform: "darwin" });
  const library = await loadSeedLibrary();

  const answers = [...wizardAnswers({ library, skill: "tests-that-catch-bugs" })];
  const output: string[] = [];

  const result = await runWizard({
    paths,
    library,
    answer: () => answers.shift() ?? null,
    confirm: () => false,
    writeLine: (line) => output.push(line),
  });

  expect(result.written).toBeFalse();
  expect(result.selectedGuidanceIds).toHaveLength(5);

  for (const guidanceId of result.selectedGuidanceIds) {
    const entry = library.guidance.find(
      (candidate) => candidate.id === guidanceId,
    );

    expect(entry ? output.includes(`  ${entry.title}`) : false).toBeTrue();
  }

  expect(await Bun.file(paths.profileDirectory).exists()).toBeFalse();
});

test("writes stable declared rules on identical reruns", async () => {
  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-wizard-"),
  );
  const paths = createProjectPaths({ homeDirectory, platform: "darwin" });
  const library = await loadSeedLibrary();

  for (let runNumber = 0; runNumber < 2; runNumber += 1) {
    const answers = [...wizardAnswers({ library, skill: "tests-that-catch-bugs" })];

    await runWizard({
      paths,
      library,
      answer: () => answers.shift() ?? null,
      confirm: () => true,
      writeLine: () => {},
    });
  }

  const rules = (await readProfileSnapshot(paths)).rules.map(
    ({ rule }) => rule,
  );
  const testingSkill = rules.find(
    (rule) => rule.key === seedGuidanceProfileKey("tests-that-catch-bugs"),
  );

  expect(rules).toHaveLength(4);
  expect(rules.every((rule) => rule.source === "declared")).toBeTrue();
  expect(rules.every((rule) => rule.key.startsWith("seed:"))).toBeTrue();
  expect(testingSkill).toBeUndefined();

  for (const root of [
    path.join(homeDirectory, ".agents/skills"),
    path.join(homeDirectory, ".claude/skills"),
    path.join(homeDirectory, ".gemini/config/skills"),
  ]) {
    const skill = await Bun.file(
      path.join(root, "tests-that-catch-bugs/SKILL.md"),
    ).text();

    expect(skill).toContain("# Tests That Catch Bugs");
  }

  for (const redundantRoot of [".codex/skills", ".cursor/skills"]) {
    expect(
      await Bun.file(
        path.join(homeDirectory, redundantRoot, "tests-that-catch-bugs/SKILL.md"),
      ).exists(),
    ).toBeFalse();
  }

  expect(await Bun.file(paths.profileManifestFile).exists()).toBeFalse();
});
