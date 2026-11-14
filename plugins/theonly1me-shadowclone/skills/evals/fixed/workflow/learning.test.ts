import { expect, test } from "bun:test";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { prepareWorkflowEnvironments } from "./preparation";
import { learnWorkflowEnvironments, readPreparedEnvironments } from "./learning";
import { syntheticLearner } from "./syntheticLearner";
import { existingSkill, workflowDefinition } from "./definition";
import { prepareWorkflowSuite, readWorkflowSuite } from "./freeze";

test("synthetic corrections travel through capture, redaction, extraction, review, publication, and both host freezes", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "four-setup-learning-"));
  try {
    const preparationFile = await prepareWorkflowEnvironments({
      directory: path.join(directory, "environments"),
      engine: "codex",
      model: "synthetic-model",
      effort: "medium",
      maximumCalls: 16,
      cliVersion: "synthetic-cli",
    });
    const prompts: string[] = [];
    const runner = syntheticLearner({ prompts });
    const result = await learnWorkflowEnvironments({
      preparationFile,
      managedConfigPath: null,
      runner: async (options) => {
        expect(options.model).toBe("synthetic-model");
        expect(options.effort).toBe("medium");
        expect(options.access).toBe("none");
        expect(options.memoryEnabled).toBeFalse();
        expect(options.expectedCliVersion).toBe("synthetic-cli");
        expect(options.signal).toBeDefined();
        return runner(options);
      },
    });
    expect(result.learning.outcome).toBe("complete");
    expect(result.learning.calls.length).toBeGreaterThan(0);
    expect(result.learning.calls.length).toBeLessThanOrEqual(16);
    expect(result.learning.publishedRules).toBe(2);
    const prepared = await readPreparedEnvironments(result.environmentsFile);
    for (const prompt of prompts)
      for (const task of workflowDefinition.tasks) expect(prompt).not.toContain(task.turns[0]);
    for (const engine of ["codex", "claude-code"] as const) {
      const deep = prepared.engines[engine].deep;
      expect(deep.files.some((file) => file.content.includes("at most 80 words"))).toBeTrue();
      expect(
        deep.files.some((file) => file.content.includes("never create a Git commit")),
      ).toBeTrue();
      expect(
        deep.files
          .filter((file) => file.path.includes("/personal-engineering/"))
          .every((file) => file.content === existingSkill),
      ).toBeTrue();
      const suiteFile = await prepareWorkflowSuite({
        environmentsFile: result.environmentsFile,
        directory: path.join(directory, engine),
        engine,
        model: "synthetic-scored",
        effort: "high",
        repetitions: 3,
        cliVersion: "synthetic-cli",
      });
      const frozen = await readWorkflowSuite(suiteFile);
      expect(frozen.suite.limits.maximumCalls).toBe(96);
      expect(frozen.suite.tasks).toHaveLength(7);
      expect(frozen.suite.arms.deep).toEqual(deep);
    }
    await expect(
      learnWorkflowEnvironments({ preparationFile, managedConfigPath: null, runner }),
    ).rejects.toThrow();
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("failed learning retains its charged invocation and cannot produce a scored suite", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "four-setup-failed-learning-"));
  try {
    const preparationFile = await prepareWorkflowEnvironments({
      directory,
      engine: "codex",
      model: "synthetic-model",
      effort: "medium",
      maximumCalls: 1,
      cliVersion: "synthetic-cli",
    });
    const result = await learnWorkflowEnvironments({
      preparationFile,
      managedConfigPath: null,
      runner: async (options) => {
        await options.debugTransport?.({
          stdout: "Synthetic failed native transport.",
          stderr: "Synthetic native failure.",
        });
        throw new Error("Synthetic engine failure");
      },
    });
    expect(result.learning.outcome).toBe("incomplete");
    expect(result.learning.calls).toHaveLength(1);
    expect(result.learning.calls[0]?.isError).toBeTrue();
    const diagnostics = await Array.fromAsync(
      new Bun.Glob("learning/call-*-diagnostic.json").scan({ cwd: directory }),
    );
    const transports = await Array.fromAsync(
      new Bun.Glob("learning/call-*-transport.json").scan({ cwd: directory }),
    );
    expect(diagnostics).toHaveLength(1);
    expect(transports).toHaveLength(1);
    const diagnostic = diagnostics[0];
    const transport = transports[0];
    if (!diagnostic || !transport) throw new Error("Missing retained native evidence.");
    expect(await Bun.file(path.join(directory, diagnostic)).json()).toMatchObject({
      message: "Synthetic engine failure",
      confirmedInfrastructure: false,
    });
    expect(await Bun.file(path.join(directory, transport)).json()).toMatchObject({
      stdout: "Synthetic failed native transport.",
    });
    await expect(readPreparedEnvironments(result.environmentsFile)).rejects.toThrow("incomplete");
    await expect(
      learnWorkflowEnvironments({ preparationFile, managedConfigPath: null }),
    ).rejects.toThrow("already attempted");
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
