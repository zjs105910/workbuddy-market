import { expect, test } from "bun:test";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { prepareFixedSuite, readFixedSuite } from "./freeze";
import { fixedDefinition } from "./definition";
import { validateFixedGraders } from "./calibration";
import { defaultManagedPolicy } from "@shadowclone/core";
import { requireFixedPolicy } from ".";

test("handwritten guidance uses maintained skills for both hosts without learning or existing private data", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "fixed-freeze-"));
  try {
    for (const engine of ["codex", "claude-code"] as const) {
      const root = path.join(directory, engine);
      const suiteFile = await prepareFixedSuite({ directory: root, engine, model: "synthetic-model", effort: "medium", repetitions: 3, cliVersion: "synthetic-cli" });
      const frozen = await readFixedSuite(suiteFile);
      expect(frozen.suite.tasks).toEqual(fixedDefinition.tasks);
      expect(frozen.suite.droppedChecks).toEqual([]);
      expect(frozen.suite.memory).toEqual([]);
      expect(frozen.suite.limits.maximumCalls).toBe(72);
      expect(frozen.suite.arms.original.files[0]?.content).toBe(fixedDefinition.profileText);
      const skills = frozen.suite.arms["first-time"].files.filter((file) => file.path.endsWith("SKILL.md"));
      expect(skills.length).toBeGreaterThan(0);
      expect(skills.every((file) => fixedDefinition.profile.every((rule) => file.content.includes(rule.statement)))).toBe(true);
      expect(frozen.suite.arms["first-time"].files.some((file) => file.content.includes("Use the engineering-preferences skill"))).toBe(true);
      expect(frozen.suite.arms["first-time"].files.every((file) => !file.content.includes(directory))).toBe(true);
      await expect(prepareFixedSuite({ directory: root, engine, model: "synthetic-model", effort: "medium", repetitions: 3, cliVersion: "synthetic-cli" })).rejects.toThrow("new directory");
      await Bun.write(suiteFile, JSON.stringify({ ...frozen, suite: { ...frozen.suite, model: "changed-model" } }));
      await expect(readFixedSuite(suiteFile)).rejects.toThrow("Frozen inputs changed");
    }
  } finally { await rm(directory, { recursive: true, force: true }); }
});

test("each fixed grader passes positive evidence, fails negative evidence, and is stable", () => {
  const result = validateFixedGraders();
  expect(result.passed).toBe(true);
  expect(result.results).toHaveLength(26);
});

test("capture and distillation are not prerequisites, but managed native action limits remain authoritative", () => {
  expect(() => requireFixedPolicy({ engine: "codex", policy: { ...defaultManagedPolicy, allowedSources: [], distillation: "disabled" } })).not.toThrow();
  expect(() => requireFixedPolicy({ engine: "codex", policy: { ...defaultManagedPolicy, enabled: false } })).toThrow("policy");
  expect(() => requireFixedPolicy({ engine: "codex", policy: { ...defaultManagedPolicy, allowedEngines: ["claude-code"] } })).toThrow("policy");
  expect(() => requireFixedPolicy({ engine: "codex", policy: { ...defaultManagedPolicy, maxActionTier: "draft" } })).toThrow("policy");
});
