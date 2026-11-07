import { expect, test } from "bun:test";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { readConfig } from "@shadowclone/core";
import { prepareWorkflowEnvironments, readWorkflowPreparation, requirePreparationInputs } from "./preparation";
import { existingSkill, workflowDefinition } from "./definition";
import { captureWorkflowArm, workflowLayout } from "./layout";

test("routing preparation preserves synthetic skills, never learns, and starts deep identically on both hosts", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "four-setup-preparation-"));
  try {
    const file = await prepareWorkflowEnvironments({ directory, engine: "codex", model: "synthetic-model", effort: "medium", maximumCalls: 16, cliVersion: "synthetic-cli" });
    const preparation = await readWorkflowPreparation(file);
    const layout = workflowLayout(directory);
    expect(await Bun.file(path.join(layout.learning, "budget.json")).exists()).toBeFalse();
    for (const engine of ["codex", "claude-code"] as const) {
      const original = preparation.starting[engine].original;
      expect(original.files.filter(file => file.path.includes("/personal-engineering/")).every(file => file.content === existingSkill)).toBeTrue();
      const routing = preparation.starting[engine]["first-time"];
      expect(routing.files.some(file => file.content.includes("Shadowclone"))).toBeTrue();
      for (const rule of workflowDefinition.profile.filter(rule => rule.group === "learned")) expect(routing.files.some(file => file.content.includes(rule.statement))).toBeFalse();
      expect(await captureWorkflowArm({ directory, arm: "deep", engine })).toEqual(routing);
    }
    const config = await readConfig({ configPath: layout.paths("deep").configFile });
    expect(config.sources["claude-code"]).toBeFalse();
    expect(Object.entries(config.sources).filter(([, enabled]) => enabled).map(([source]) => source)).toEqual(["skill-library"]);
    expect(config.distillation).toEqual({ deep: false, automatic: false });
    await requirePreparationInputs({ directory, preparation, beforeLearning: true });
    const originalConfig = await Bun.file(layout.paths("deep").configFile).text();
    await Bun.write(layout.paths("deep").configFile, `${originalConfig}\n`);
    await expect(requirePreparationInputs({ directory, preparation, beforeLearning: true })).rejects.toThrow("configuration or state changed");
    await Bun.write(layout.paths("deep").configFile, originalConfig);
    await Bun.write(path.join(layout.paths("deep").claudeProjectsDirectory, "synthetic-persona", "extra.jsonl"), "changed");
    await expect(requirePreparationInputs({ directory, preparation, beforeLearning: true })).rejects.toThrow("corpus changed");
    await expect(prepareWorkflowEnvironments({ directory, engine: "codex", model: "synthetic-model", effort: "medium", maximumCalls: 16, cliVersion: "synthetic-cli" })).rejects.toThrow("empty");
  } finally { await rm(directory, { recursive: true, force: true }); }
});
