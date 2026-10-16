import { expect, test } from "bun:test";
import { createLearningExecution, defaultLearningExecutionLimits } from "@shadowclone/agents";
import { fingerprint } from "@shadowclone/core";
import { learningRecord, skillEngineRun, skillFixture } from "@shadowclone/environment/testing";
import {
  emptyEnvironment,
  pendingLearningRecords,
  readEnvironment,
  writeEnvironment,
} from "@shadowclone/environment";
import { updateLearningEnvironment } from "./update";

const matchingEdit = { before: "Preserve the requested behavior." };
const missingEdit = { before: "This sentence is not in the skill." };

async function learnWith(options: {
  readonly drafts: readonly (typeof matchingEdit)[];
  readonly maximumCalls?: number;
}) {
  const setup = await skillFixture();
  const record = learningRecord();
  const prompts: string[] = [];
  const drafts = [...options.drafts];
  const original = await Bun.file(setup.filePath).text();

  await writeEnvironment({
    paths: setup.paths,
    state: { ...emptyEnvironment, automatic: true, records: [record] },
  });

  const execution = createLearningExecution({
    engine: "claude-code",
    limits: {
      ...defaultLearningExecutionLimits,
      maximumCalls: options.maximumCalls ?? defaultLearningExecutionLimits.maximumCalls,
    },
    runner: async (run) => {
      prompts.push(run.prompt);

      if (run.prompt.includes("Organize durable")) {
        return skillEngineRun({
          routes: [
            {
              key: record.rule.key,
              destination: "skill",
              skillId: fingerprint(setup.filePath),
              name: "typed-changes",
              description: "Use for typed changes",
              reason: "Applies to this workflow",
            },
          ],
        });
      }

      const edit = drafts.shift() ?? missingEdit;

      return skillEngineRun({
        outcomes: [{ key: record.rule.key, disposition: "apply", reason: "Supported" }],
        description: "Make typed code changes and validate sample palettes.",
        body: "",
        edits: [{ ...edit, after: `${edit.before} ${record.rule.body}`, keys: [record.rule.key] }],
      });
    },
  });
  const summary = await updateLearningEnvironment({ ...setup, execution });
  const state = await readEnvironment(setup.paths);

  if (state === null) {
    throw new Error("The update did not keep an environment.");
  }

  return {
    summary,
    prompts,
    original,
    skill: await Bun.file(setup.filePath).text(),
    reason: pendingLearningRecords({ paths: setup.paths, state }).find(
      (entry) => entry.key === record.rule.key,
    )?.reason,
    body: record.rule.body,
  };
}

test("a draft that fails validation gets one repair turn with the exact error, then publishes", async () => {
  const result = await learnWith({ drafts: [missingEdit, matchingEdit] });

  expect(result.summary?.applied).toBe(1);
  expect(result.skill).toContain(result.body);
  expect(result.prompts).toHaveLength(3);
  expect(result.prompts[2]).toContain(
    "Your previous draft failed host validation with this error: Skill edit does not match one exact section.",
  );
});

test("a draft that still fails after the repair stays pending with both errors", async () => {
  const result = await learnWith({ drafts: [missingEdit, missingEdit] });

  expect(result.summary?.applied).toBe(0);
  expect(result.skill).toBe(result.original);
  expect(result.reason).toBe(
    "Validate sample palette entries: The draft failed validation: Skill edit does not match one exact section. One repair turn also failed: Skill edit does not match one exact section. Review the target document and retry this learning.",
  );
});

test("a draft with no call left for a repair stays pending with its error", async () => {
  const result = await learnWith({ drafts: [missingEdit, matchingEdit], maximumCalls: 2 });

  expect(result.prompts).toHaveLength(2);
  expect(result.reason).toBe(
    "Validate sample palette entries: The draft failed validation: Skill edit does not match one exact section. No learning call was left for a repair turn. Retry this learning.",
  );
});
