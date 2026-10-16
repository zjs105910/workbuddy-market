import { expect, test } from "bun:test";
import { resolveSeedDirectories } from "@shadowclone/core";
import { loadSeedLibrary } from "./index";

const preferenceIds = [
  "dependencies-existing",
  "dependencies-mature",
  "planning-first",
  "planning-when-costly",
  "questions-autonomous",
  "questions-early",
  "refactor-boundaries",
  "refactor-preserve",
];

const skillIds = [
  "choose-by-consequence",
  "design-deep-modules",
  "diagnose-before-editing",
  "plan-with-review-page",
  "research-primary-sources",
  "resolve-conflicts-by-intent",
  "scope-confirmed-changes",
  "shadowclone-review",
  "shadowclone-work",
  "tests-that-catch-bugs",
  "typescript-type-safety",
  "verify-and-review",
  "verify-review-findings",
  "write-plain-english",
];

async function packageDirectories(): Promise<{
  readonly preferencesDirectory: string;
  readonly skillsDirectory: string;
}> {
  const seeds = await resolveSeedDirectories();

  return {
    preferencesDirectory: seeds.preferences,
    skillsDirectory: seeds.skills,
  };
}

test("loads preferences and Agent Skills into honest groups", async () => {
  const library = await loadSeedLibrary(await packageDirectories());

  expect(library.preferences.map((entry) => entry.id)).toEqual(preferenceIds);
  expect(library.skills.map((entry) => entry.id)).toEqual(skillIds);
  expect(library.guidance).toHaveLength(22);
  expect(library.axes.map((axis) => [axis.id, axis.guidance.length])).toEqual([
    ["dependency-posture", 2],
    ["planning-threshold", 2],
    ["question-frequency", 2],
    ["refactor-tolerance", 2],
  ]);
  expect(library.independentSkills).toHaveLength(14);
  expect(
    library.guidance.some((entry) => entry.id.startsWith("comments-")),
  ).toBeFalse();
});

test("loads every Agent Skill with its routing and workflow contract", async () => {
  const library = await loadSeedLibrary(await packageDirectories());

  for (const skill of library.skills) {
    expect(skill.description.length).toBeGreaterThan(40);
    expect(skill.body).toContain("## Use when");
    expect(skill.body).toContain("## Process");
    expect(skill.body).toContain("## Guardrails");
    expect(skill.body).toContain("## Completion");
  }
});
