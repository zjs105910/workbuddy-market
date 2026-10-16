import { expect, spyOn, test } from "bun:test";
import { mkdtemp, rm, mkdir } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { z } from "zod";
import { learn } from "@shadowclone/cli";
import { readConfig, writeConfig } from "@shadowclone/core";
import { evaluationBudget } from "../../shared/accounting";
import { workflowLearningRunner } from "../workflow/learner";
import type { LearnerConfiguration, LearningCall } from "../workflow/schema";
import { engineRun } from "../../native/study/fixtures";
import {
  prepareManualEnvironment,
  materializeCorpus,
  captureEnvironment,
  requireManualPreserved,
  reusableLayout,
} from "./environments";
import { developmentCases } from "./definition";
import { existingManualSkill } from "./guidance";
import { preparationLearningLimits } from "./learningLimits";

const learningsSchema = z.object({
  learnings: z.array(z.object({ key: z.string(), text: z.string() })),
});

function fixtureOutput(prompt: string): unknown {
  if (prompt.includes("Reconcile correction evidence")) {
    const evidence = prompt.split("Correction evidence\n").at(-1) ?? "";
    const block = evidence
      .split(/(?=evidence-\d+ \[)/)
      .find((block) => block.includes("eighty words"));
    const token = block?.match(/^evidence-\d+/)?.[0];
    return {
      existingRules: [],
      newRules: token
        ? [
            {
              title: "Answer length",
              body: "Keep final answers at most eighty words unless the current request asks for a different length.",
              section: "workflow",
              observed: "Global standing correction",
              evidenceTokens: [token],
              rejectionToken: "",
            },
          ]
        : [],
      assessments: token
        ? [
            {
              evidenceToken: token,
              intent: "preference",
              durable: true,
              explicit: true,
              scope: "global",
            },
          ]
        : [],
    };
  }
  if (prompt.includes("Merge duplicates into one rule"))
    return {
      dropped: [],
      rules: [
        ...prompt.matchAll(/\[(\d+)\] Title: ([^\n]+)\nBody: ([^\n]+)\nSection: ([^\n]+)/g),
      ].map((match) => ({
        title: match[2],
        body: match[3],
        section: match[4],
        sources: [Number(match[1])],
      })),
    };
  if (prompt.includes("Review skill catalog overlap")) return { overlaps: [] };
  const data = learningsSchema.parse(JSON.parse(prompt.split("\n\n").at(-1) ?? "null"));
  if (prompt.includes("Organize durable user learning"))
    return {
      routes: data.learnings.map((learning) => ({
        key: learning.key,
        destination: "baseline",
        skillId: "",
        name: "shadowclone-baseline",
        description: "Working defaults",
        reason: "Global standing correction",
      })),
    };
  if (prompt.includes("Maintain one portable skill"))
    return {
      body: "",
      description: "",
      edits: [
        {
          before: "",
          after: data.learnings.map((learning) => learning.text).join("\n\n"),
          keys: data.learnings.map((learning) => learning.key),
        },
      ],
      outcomes: data.learnings.map((learning) => ({
        key: learning.key,
        disposition: "apply",
        reason: "Preserves correction conditions",
      })),
    };
  throw new Error("Unexpected offline learner prompt.");
}

test("three isolated preparations use eligible correction text and retain incomplete rule coverage", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "v3-learning-pipeline-"));
  const allPrompts: string[] = [];
  try {
    for (const preparation of [0, 1, 2]) {
      const arm = `deep-${preparation}`;
      await prepareManualEnvironment({ directory, arm, routed: true });
      await materializeCorpus({ directory, preparation });
      const layout = reusableLayout(directory);
      const paths = layout.paths(arm);
      const before = await captureEnvironment({
        directory,
        arm,
        repository: "atlas",
        engine: "codex",
      });
      const config = await readConfig({ configPath: paths.configFile });
      await writeConfig({
        configPath: paths.configFile,
        config: {
          ...config,
          sources: { ...config.sources, "claude-code": true },
          distillation: { deep: true, automatic: false },
        },
      });
      const callDirectory = path.join(directory, "calls", String(preparation));
      await mkdir(callDirectory, { recursive: true, mode: 0o700 });
      const budget = await evaluationBudget({
        directory: callDirectory,
        resume: false,
        maximumCalls: 16,
      });
      const calls: LearningCall[] = [];
      await learn({
        paths,
        workingDirectory: layout.workspace({ arm, repository: "atlas" }),
        managedConfigPath: null,
        deep: true,
        apply: true,
        confirm: () => true,
        engine: "codex",
        model: "synthetic",
        reasoningEffort: "medium",
        maximumCalls: 16,
        writeLine: () => {},
        runner: workflowLearningRunner({
          directory: callDirectory,
          budget,
          configuration: {
            engine: "codex",
            model: "synthetic",
            effort: "medium",
            cliVersion: "synthetic-cli",
            maximumCalls: 16,
            callSeconds: 120,
            deadlineSeconds: 1200,
          },
          blockedPaths: [directory, process.cwd()],
          calls,
          runner: async (options) => {
            allPrompts.push(options.prompt);
            expect(options.access).toBe("none");
            expect(options.memoryEnabled).toBe(false);
            expect(options.prompt).not.toContain("always force push");
            for (const entry of developmentCases)
              expect(options.prompt).not.toContain(entry.task.turns[0] ?? "impossible");
            return engineRun({
              resolvedModel: "synthetic",
              cliVersion: "synthetic-cli",
              actions: [],
              structured: fixtureOutput(options.prompt),
            });
          },
        }),
      });
      expect(calls.length).toBeGreaterThan(0);
      expect(calls.length).toBeLessThanOrEqual(16);
      const after = await captureEnvironment({
        directory,
        arm,
        repository: "atlas",
        engine: "codex",
      });
      requireManualPreserved({ original: before, candidate: after });
      expect(after.files.some((file) => file.content.includes("at most eighty words"))).toBe(true);
      expect(
        after.files
          .filter((file) => file.path.includes("personal-engineering"))
          .every((file) => file.content === existingManualSkill),
      ).toBe(true);
      expect(after.files.some((file) => file.content.includes("one-sentence checklist"))).toBe(
        false,
      );
    }
    expect(allPrompts.length).toBeGreaterThan(3);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
}, 30000);

test("the frozen twenty-minute limit reaches production learning and publication beyond four minutes", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "v3-learning-deadline-"));
  let clock = Date.now();
  const now = spyOn(Date, "now").mockImplementation(() => clock);
  try {
    await prepareManualEnvironment({ directory, arm: "deep-0", routed: true });
    await materializeCorpus({ directory, preparation: 0 });
    const layout = reusableLayout(directory);
    const paths = layout.paths("deep-0");
    const config = await readConfig({ configPath: paths.configFile });
    await writeConfig({
      configPath: paths.configFile,
      config: {
        ...config,
        sources: { ...config.sources, "claude-code": true },
        distillation: { deep: true, automatic: false },
      },
    });
    const learner: LearnerConfiguration = {
      engine: "codex",
      model: "synthetic",
      effort: "medium",
      cliVersion: "synthetic-cli",
      maximumCalls: 16,
      callSeconds: 120,
      deadlineSeconds: 1200,
    };
    const callDirectory = path.join(directory, "calls");
    await mkdir(callDirectory, { mode: 0o700 });
    const budget = await evaluationBudget({
      directory: callDirectory,
      resume: false,
      maximumCalls: 16,
    });
    const calls: LearningCall[] = [];
    const lines: string[] = [];
    let invocations = 0;
    await learn({
      paths,
      workingDirectory: layout.workspace({ arm: "deep-0", repository: "atlas" }),
      managedConfigPath: null,
      deep: true,
      apply: true,
      confirm: () => true,
      engine: "codex",
      maximumCalls: 16,
      limits: preparationLearningLimits(learner),
      writeLine: (line) => lines.push(line),
      runner: workflowLearningRunner({
        directory: callDirectory,
        budget,
        configuration: learner,
        calls,
        blockedPaths: [directory, process.cwd()],
        runner: async (options) => {
          invocations += 1;
          if (invocations === 1) clock += 240001;
          return engineRun({
            resolvedModel: "synthetic",
            cliVersion: "synthetic-cli",
            actions: [],
            structured: fixtureOutput(options.prompt),
          });
        },
      }),
    });
    expect(invocations).toBeGreaterThan(1);
    expect(calls.every((call) => !call.isError)).toBe(true);
    expect(lines.some((line) => line.includes("16 total calls and 1200 seconds"))).toBe(true);
    const after = await captureEnvironment({
      directory,
      arm: "deep-0",
      repository: "atlas",
      engine: "codex",
    });
    expect(after.files.some((file) => file.content.includes("at most eighty words"))).toBe(true);
  } finally {
    now.mockRestore();
    await rm(directory, { recursive: true, force: true });
  }
}, 30000);
