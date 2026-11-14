import { expect, test } from "bun:test";
import { buildFixture } from "@shadowclone/builds/testing";
import { defaultConfig, writeConfig } from "@shadowclone/core";
import { generationResult, syntheticBrief, syntheticSkill } from "./fixtures";
import { createSkillDrafts } from "./skillDrafts";

test("browser previews identify the selected model and cache results separately for each model", async () => {
  const context = await buildFixture();
  const models: (string | undefined)[] = [];
  const drafts = createSkillDrafts({ ...context, engine: {
    engine: "claude-code",
    runner: async run => {
      models.push(run.model);
      return generationResult(syntheticSkill);
    },
  } });
  const selectModel = (model: string) => writeConfig({ configPath: context.paths.configFile, config: {
    ...defaultConfig, distillation: { deep: true, engine: "claude-code", model },
  } });
  await selectModel("synthetic-first");
  const first = await drafts.preview(syntheticBrief);
  expect(first.destination).toBe("claude-code using synthetic-first");
  await drafts.generate({ id: first.id });
  expect(models).toEqual(["synthetic-first"]);
  const repeated = await drafts.preview(syntheticBrief);
  expect(repeated.cached).toEqual(syntheticSkill);
  await selectModel("synthetic-second");
  const second = await drafts.preview(syntheticBrief);
  expect(second.destination).toBe("claude-code using synthetic-second");
  expect(second.cached).toBeNull();
  await drafts.generate({ id: second.id });
  expect(models).toEqual(["synthetic-first", "synthetic-second"]);
});
