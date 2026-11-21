import { expect, test } from "bun:test";
import path from "node:path";
import { defaultConfig, writeConfig } from "@shadowclone/core";
import {
  createLearningExecution,
  type EngineRun,
  type EngineRunner,
} from "@shadowclone/agents";
import { runLearningMaintenance } from "..";
import { skillEngineRun, skillExecution, skillFixture } from "@shadowclone/environment/testing";
import { readMaintenanceState } from "@shadowclone/skills";
import { updateSkillLibrary, type SkillUpdateSummary } from "./update";
import { fixtureSkill } from "@shadowclone/skills/testing";

function failedSkillRun(): EngineRun {
  return {
    ...skillEngineRun(null),
    costUsd: null,
    isError: true,
    errorMessage: "Maximum budget reached",
  };
}

test("large libraries leave unassessed roots for the next bounded run", async () => {
  const setup = await skillFixture();

  await Bun.write(
    path.join(setup.home, ".agents/skills/workflow-checks/SKILL.md"),
    fixtureSkill("workflow-checks"),
  );

  const first = await updateSkillLibrary({
    ...setup,
    execution: skillExecution({ maximumCalls: 1 }),
  });

  expect(first).toMatchObject({ assessed: 1, deferred: 1 });

  const second = await updateSkillLibrary({
    ...setup,
    execution: skillExecution({ maximumCalls: 1 }),
  });

  expect(second).toMatchObject({ assessed: 1, deferred: 0 });
});

test("recent profile learning and skill assessment share one model allowance", async () => {
  const setup = await skillFixture();
  const now = Date.parse("2026-09-11T10:00:00Z");

  await writeConfig({
    configPath: setup.paths.configFile,
    config: {
      ...defaultConfig,
      sources: {
        ...defaultConfig.sources,
        "skill-library": true,
        "claude-code": true,
      },
      distillation: { deep: true, automatic: false },
    },
  });
  await Bun.write(
    path.join(setup.paths.claudeProjectsDirectory, "fixture/session.jsonl"),
    `${JSON.stringify({ type: "user", sessionId: "one", uuid: "event-one", timestamp: new Date(now - 1000).toISOString(), cwd: setup.cwd, message: { content: "Always use complete variable names." } })}\n`,
  );

  const runner: EngineRunner = () =>
    Promise.resolve(
      skillEngineRun({
        existingRules: [],
        newRules: [],
        assessments: [
          {
            evidenceToken: ["evidence", "1"].join("-"),
            intent: "preference",
            durable: true,
            scope: "repository",
          },
        ],
      }),
    );

  const execution = createLearningExecution({
    engine: "claude-code",
    runner,
    limits: {
      maximumCalls: 1,
      timeoutMilliseconds: 300_000,
      maximumCostUsd: 2,
    },
  });

  const summaries: SkillUpdateSummary[] = [];

  expect(
    await runLearningMaintenance({
      ...setup,
      automatic: false,
      now,
      runner,
      engine: "claude-code",
      execution,
      reportSkills: (summary) => {
        summaries.push(summary);
      },
    }),
  ).toBe("completed");
  expect(execution.callsUsed()).toBe(1);
  expect(summaries[0]).toMatchObject({ assessed: 0, deferred: 1 });
});

test("engine failures defer skill assessment and preserve it for the next run", async () => {
  const setup = await skillFixture();

  await Bun.write(
    path.join(setup.home, ".agents/skills/workflow-checks/SKILL.md"),
    fixtureSkill("workflow-checks"),
  );

  let calls = 0;

  const runner: EngineRunner = () => {
    calls += 1;

    return Promise.resolve(
      calls === 1
        ? failedSkillRun()
        : skillEngineRun({
            assessments: [
              {
                token: "skill-1",
                decision: "keep",
                description: "",
                passages: [],
                findings: [],
              },
            ],
          }),
    );
  };

  const firstExecution = createLearningExecution({
    engine: "claude-code",
    runner,
  });
  const first = await updateSkillLibrary({
    ...setup,
    execution: firstExecution,
  });

  expect(first).toMatchObject({ assessed: 0, deferred: 2 });
  expect((await readMaintenanceState(setup.paths)).assessed).toEqual({});

  const secondExecution = createLearningExecution({
    engine: "claude-code",
    runner,
  });
  const second = await updateSkillLibrary({
    ...setup,
    execution: secondExecution,
  });

  expect(second).toMatchObject({ assessed: 2, deferred: 0 });
});

test("thrown engine failures defer skill assessment", async () => {
  const setup = await skillFixture();
  const runner: EngineRunner = () =>
    Promise.reject(new Error("Engine stopped"));
  const execution = createLearningExecution({ engine: "claude-code", runner });

  expect(await updateSkillLibrary({ ...setup, execution })).toMatchObject({
    assessed: 0,
    deferred: 1,
  });
});

test("successful malformed skill assessments remain invalid", async () => {
  const setup = await skillFixture();
  const runner: EngineRunner = () =>
    Promise.resolve(skillEngineRun({ assessments: [] }));
  const execution = createLearningExecution({ engine: "claude-code", runner });

  await expect(updateSkillLibrary({ ...setup, execution })).rejects.toThrow(
    "Skill assessment omitted or duplicated an input",
  );
});
