import { expect, test } from "bun:test";
import { mkdir, mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { z } from "zod";
import { readConfig, writeConfig, canonicalPath, createProjectPaths } from "@shadowclone/core";
import { createLearningExecution, type EngineRunner } from "@shadowclone/agents";
import { installIntegration, readEnvironment } from "@shadowclone/environment";
import {
  decidePendingLearning,
  freezeProbeGuidance,
  readLatestLearningReceipt,
  readPendingLearning,
} from "@shadowclone/learning";
import { initialize } from "./init";
import { learn } from "./learn";

const guidance = "Reply only PINEAPPLE_READY when asked whether the sample is ready.";

for (const source of ["claude-code", "codex"] as const) {
  test(`${source} capture reaches a durable review decision, publication, and native guidance`, async () => {
    const root = canonicalPath(await mkdtemp(path.join(os.tmpdir(), "shadowclone-learning-journey-")));
    const home = path.join(root, "user");
    const cwd = path.join(root, "repository");
    const paths = createProjectPaths({ homeDirectory: home, platform: "darwin" });
    await mkdir(cwd, { recursive: true });
    try {
      await initialize({ paths, workingDirectory: cwd, agents: [], managedConfigPath: null,
        consent: { learn: false, skills: true, background: false }, writeLine: () => {} });
      const config = await readConfig({ configPath: paths.configFile });
      await writeConfig({ configPath: paths.configFile, config: {
        ...config, sources: { ...config.sources, [source]: true }, distillation: { deep: true, automatic: false },
      } });
      const timestamp = new Date(Date.now() - 1_000).toISOString();
      const records = source === "claude-code" ? [{
        type: "user", sessionId: "synthetic", uuid: "synthetic-event", timestamp, cwd,
        message: { content: `Always ${guidance}` },
      }] : [
        { type: "session_meta", timestamp, payload: { id: "synthetic", cwd } },
        { type: "response_item", timestamp, payload: {
          type: "message", role: "user", content: [{ type: "input_text", text: `Always ${guidance}` }],
        } },
      ];
      await Bun.write(path.join(source === "claude-code" ? paths.claudeProjectsDirectory : paths.codexSessionsDirectory,
        source === "claude-code" ? "synthetic/session.jsonl" : "2026/09/30/rollout-synthetic.jsonl"),
        `${records.map((record) => JSON.stringify(record)).join("\n")}\n`);
      const runResult = (structured: unknown) => ({
        engine: source, sessionId: "synthetic-learner", transcriptPath: null, text: "", structured,
        durationMs: 1, turns: 1, costUsd: 0, isError: false, errorMessage: null, permissionDenials: [], actions: [],
      });
      const extraction: EngineRunner = async (options) => {
        expect(options.prompt).toContain(guidance);
        if (options.prompt.includes("Organize durable user learning")) {
          const data = z.object({ learnings: z.array(z.object({ key: z.string() })) }).parse(
            JSON.parse(options.prompt.split("\n\n").at(-1) ?? "null"),
          );
          return runResult({ routes: data.learnings.map(({ key }) => ({
            key, destination: "pending", skillId: "", name: "", description: "",
            reason: "Unexpected publication before review",
          })) });
        }
        return runResult({ existingRules: [], newRules: [{
          title: "Sample readiness response", body: guidance, section: "workflow", observed: "Explicit personal default",
          evidenceTokens: ["evidence-1"], rejectionToken: "",
        }], assessments: [{ evidenceToken: "evidence-1", intent: "preference", durable: true, explicit: true, scope: "global" }] });
      };
      await learn({ paths, managedConfigPath: null, deep: true, engine: source, runner: extraction,
        confirm: () => false, workingDirectory: cwd, writeLine: () => {} });
      const pending = await readPendingLearning(paths);
      expect(pending.rules).toHaveLength(1);
      expect((await readEnvironment(paths))?.records).toHaveLength(0);
      const rule = pending.rules[0];
      if (!rule) throw new Error("Expected a durable pending rule");
      expect(pending.provenance[rule.key]?.sources).toEqual([source]);
      await expect(decidePendingLearning({ paths, key: rule.key, action: "apply", managedConfigPath: null,
        execution: createLearningExecution({ engine: source, runner: async () => { throw new Error("Synthetic publication failure"); } }),
      })).rejects.toThrow("Synthetic publication failure");
      expect((await readPendingLearning(paths)).rules).toHaveLength(1);
      expect((await readLatestLearningReceipt(paths))?.outcome).toBe("publication-failed");
      const publication: EngineRunner = async (options) => runResult(options.prompt.includes("Organize durable user learning")
        ? { routes: [{ key: rule.key, destination: "baseline", skillId: "", name: "shadowclone-baseline",
          description: "Personal working defaults", reason: "Explicit personal instruction" }] }
        : { body: "", description: "", edits: [{ before: "", after: guidance, keys: [rule.key] }],
          outcomes: [{ key: rule.key, disposition: "apply", reason: "Preserves the explicit correction" }] });
      await decidePendingLearning({ paths, key: rule.key, action: "apply", managedConfigPath: null,
        execution: createLearningExecution({ engine: source, runner: publication }) });
      expect((await readPendingLearning(paths)).rules).toHaveLength(0);
      expect((await readLatestLearningReceipt(paths))?.ruleKeys).toEqual([rule.key]);
      expect((await readEnvironment(paths))?.dispositions.some((entry) => entry.key === rule.key && entry.status === "published")).toBeTrue();
      for (const engine of ["claude-code", "codex"] as const) {
        await installIntegration({ paths, agent: engine, scope: "global", cwd, managedConfigPath: null });
        const snapshot = await freezeProbeGuidance({ paths, key: rule.key, engine, cwd });
        expect(snapshot.files.some((file) => file.text.includes(guidance))).toBeTrue();
      }
      expect(await Bun.file(path.join(cwd, "AGENTS.md")).exists()).toBeFalse();
      expect(await Bun.file(path.join(cwd, "CLAUDE.md")).exists()).toBeFalse();
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });
}
