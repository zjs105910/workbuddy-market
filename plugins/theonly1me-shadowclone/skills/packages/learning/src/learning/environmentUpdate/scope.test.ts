import { expect, test } from "bun:test";
import path from "node:path";
import { mkdir } from "node:fs/promises";
import { createLearningExecution } from "@shadowclone/agents";
import { readConfig, writeConfig } from "@shadowclone/core";
import { normalizeRemoteRepository } from "@shadowclone/sessions";
import { learningRecord, skillEngineRun, skillFixture } from "@shadowclone/environment/testing";
import { configureSkillMaintenance } from "@shadowclone/skills";
import {
  emptyEnvironment,
  learningRuleSchema,
  readEnvironment,
  writeEnvironment,
} from "@shadowclone/environment";
import { updateLearningEnvironment } from "./update";

test("organization learning is published independently into each matching repository", async () => {
  const setup = await skillFixture();
  const repositories = [];

  for (const name of ["first", "second", "unrelated"]) {
    const directory = path.join(setup.home, name);

    await mkdir(directory);

    const identity = normalizeRemoteRepository(
      [
        "https://github.com",
        name === "unrelated" ? "other" : "synthetic",
        name + ".git",
      ].join("/"),
    );

    if (!identity?.profileFileName) {
      throw new Error("Expected fixture identity");
    }

    repositories.push({
      directory,
      originDirectory: identity.origin.directoryName,
      repositoryName: identity.profileFileName,
    });
    await configureSkillMaintenance({
      paths: setup.paths,
      cwd: directory,
      scope: "repository",
      managedConfigPath: null,
    });
  }

  const [first] = repositories;

  if (!first) {
    throw new Error("Expected first repository");
  }

  const fixture = learningRecord();

  const record = {
    ...fixture,
    rule: learningRuleSchema.parse({
      ...fixture.rule,
      scope: "org",
      originDirectory: first.originDirectory,
      repositoryName: null,
    }),
  };

  await writeEnvironment({
    paths: setup.paths,
    state: {
      ...emptyEnvironment,
      automatic: true,
      records: [record],
      repositories,
    },
  });

  const config = await readConfig({ configPath: setup.paths.configFile });

  await writeConfig({
    configPath: setup.paths.configFile,
    config: { ...config, sources: { ...config.sources, "git-metadata": true } },
  });

  let calls = 0;

  const execution = createLearningExecution({
    engine: "claude-code",
    runner: async (run) => {
      calls += 1;

      if (run.prompt.includes("Review skill catalog overlap")) {
        return skillEngineRun({ overlaps: [] });
      }

      return skillEngineRun(
        run.prompt.includes("Organize durable")
          ? {
              routes: [
                {
                  key: record.rule.key,
                  destination: "skill",
                  skillId: "",
                  name: "palette-check",
                  description: "When editing sample palettes",
                  reason: "Scoped workflow",
                },
              ],
            }
          : {
              outcomes: [{ key: record.rule.key, disposition: "apply", reason: "Supported" }],
              description: "",
              edits: [],
              body: ["# Palette validation", record.rule.body, ""].join("\n\n"),
            },
      );
    },
  });

  await updateLearningEnvironment({
    ...setup,
    execution,
    readRemote: async (directory) =>
      [
        "https://github.com",
        path.basename(directory) === "unrelated" ? "other" : "synthetic",
        path.basename(directory) + ".git",
      ].join("/"),
  });

  expect(calls).toBe(5);
  expect(
    await Bun.file(
      path.join(setup.home, "first/.agents/skills/palette-check/SKILL.md"),
    ).exists(),
  ).toBeTrue();
  expect(
    await Bun.file(
      path.join(setup.home, "second/.agents/skills/palette-check/SKILL.md"),
    ).exists(),
  ).toBeTrue();
  expect(
    await Bun.file(
      path.join(setup.home, "unrelated/.agents/skills/palette-check/SKILL.md"),
    ).exists(),
  ).toBeFalse();
  expect(
    await Bun.file(
      path.join(setup.home, ".agents/skills/palette-check/SKILL.md"),
    ).exists(),
  ).toBeFalse();
  expect((await readEnvironment(setup.paths))?.dispositions).toHaveLength(2);
});

test("skill source consent alone never authorizes automatic edits or model calls", async () => {
  const setup = await skillFixture();

  await writeEnvironment({
    paths: setup.paths,
    state: { ...emptyEnvironment, records: [learningRecord()] },
  });

  const execution = createLearningExecution({
    engine: "claude-code",
    runner: async () => {
      throw new Error("Automatic edits were not authorized");
    },
  });

  const summary = await updateLearningEnvironment({ ...setup, execution });

  expect(summary?.pending).toBe(1);
  expect(await Bun.file(setup.filePath).text()).toBe(setup.original);
  expect(
    await Bun.file(
      path.join(setup.home, ".agents/skills/typed-changes/SKILL.md"),
    ).exists(),
  ).toBeFalse();
});
