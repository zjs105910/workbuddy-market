import { expect, test } from "bun:test";
import { rm } from "node:fs/promises";
import path from "node:path";
import { integrationFixture } from "@shadowclone/core/testing";
import { installIntegration, nativeSessionEnd } from "@shadowclone/environment";
import { defaultConfig, writeConfig } from "@shadowclone/core";
import { runAutomaticLearning } from "./worker";
import { readLearningState } from "./state";
import type { EngineRunner } from "@shadowclone/agents";

test("settled and shutdown requests share the learning ledger and inherit the triggering Pi model", async () => {
  const fixture = await integrationFixture();
  try {
    await writeConfig({ configPath: fixture.paths.configFile, config: {
      ...defaultConfig, sources: { ...defaultConfig.sources, pi: true },
      distillation: { deep: true, automatic: true, engine: "codex", model: "saved-model" },
    } });
    const integration = await installIntegration({ ...fixture, agent: "pi", scope: "global" });
    const sourcePath = path.join(fixture.paths.piSessionsDirectory, "synthetic/session.jsonl");
    await Bun.write(sourcePath, [
      { type: "session", version: 3, id: "synthetic", cwd: fixture.cwd },
      { type: "message", id: "prompt", parentId: null, timestamp: "2026-10-01T00:00:00.000Z", message: { role: "user", content: "Always use explicit parameter names." } },
    ].map(value => JSON.stringify(value)).join("\n") + "\n");
    const sessionKey = await nativeSessionEnd({ ...fixture, id: integration.id, input: JSON.stringify({ cwd: fixture.cwd, session_id: "synthetic" }) });
    if (!sessionKey) throw new Error("Missing synthetic session identity");
    const models: (string | undefined)[] = [];
    const runner: EngineRunner = async options => {
      models.push(options.model);
      return { engine: "pi", sessionId: "synthetic-learning", transcriptPath: null, text: "", structured: { existingRules: [], newRules: [], assessments: [] }, costUsd: null, durationMs: 0, turns: 1, isError: false, permissionDenials: [], actions: [], errorMessage: null };
    };
    const request = { ...fixture, runner, engine: "pi" as const, model: "session-provider/local", sessionKeys: [sessionKey] };
    expect(await runAutomaticLearning(request)).toBe("completed");
    expect(await runAutomaticLearning(request)).toBe("completed");
    expect(models).toEqual(["session-provider/local"]);
    expect((await readLearningState(fixture.paths)).processed).toHaveLength(1);
  } finally { await rm(fixture.home, { recursive: true, force: true }); }
});
