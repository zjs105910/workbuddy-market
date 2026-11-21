import { expect, test } from "bun:test";
import { createLearningExecution, type EngineRunner } from "@shadowclone/agents";
import { skillEngineRun, skillFixture } from "@shadowclone/environment/testing";
import { updateSkillLibrary } from "./update";

function validAssessment(options: { readonly description?: string } = {}) {
  return {
    assessments: [
      {
        token: "skill-1",
        decision: "keep",
        description: options.description ?? "",
        passages: [],
        findings: [],
      },
    ],
  };
}

test("skill assessment omits unsupported structured output limits", async () => {
  const setup = await skillFixture();
  let serializedSchema = "";
  const runner: EngineRunner = (run) => {
    serializedSchema = JSON.stringify(run.outputSchema);

    return Promise.resolve(skillEngineRun(validAssessment()));
  };
  const execution = createLearningExecution({ engine: "claude-code", runner });

  expect(await updateSkillLibrary({ ...setup, execution })).toMatchObject({
    assessed: 1,
    deferred: 0,
  });
  expect(serializedSchema).not.toContain('"minLength"');
  expect(serializedSchema).not.toContain('"maxLength"');
  expect(serializedSchema).not.toContain('"maxItems"');
});

test("skill assessment keeps output limits in local validation", async () => {
  const setup = await skillFixture();
  const runner: EngineRunner = () =>
    Promise.resolve(
      skillEngineRun(validAssessment({ description: "x".repeat(1_025) })),
    );
  const execution = createLearningExecution({ engine: "claude-code", runner });

  await expect(updateSkillLibrary({ ...setup, execution })).rejects.toThrow(
    "Invalid skill assessment response",
  );
});
