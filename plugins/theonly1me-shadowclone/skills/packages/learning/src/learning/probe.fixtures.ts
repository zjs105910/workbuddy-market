import { mkdtemp, mkdir } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { defaultConfig, writeConfig, canonicalPath, createProjectPaths } from "@shadowclone/core";
import { learningRecord } from "@shadowclone/environment/testing";
import {
  emptyEnvironment,
  installIntegration,
  recordFingerprint,
  writeEnvironment,
} from "@shadowclone/environment";
import type { NativeEngine, NativeEngineRun } from "@shadowclone/agents";

export async function probeFixture(engine: NativeEngine) {
  const root = canonicalPath(await mkdtemp(path.join(os.tmpdir(), "shadowclone-probe-fixture-")));
  const home = path.join(root, "user");
  const cwd = path.join(root, "repository");
  await mkdir(cwd, { recursive: true });
  const paths = createProjectPaths({ homeDirectory: home, platform: "darwin" });
  const record = learningRecord({ key: "ready-reply", body: "When asked whether the sample is ready, reply only PINEAPPLE_READY." });
  await writeConfig({ configPath: paths.configFile, config: {
    ...defaultConfig, sources: { ...defaultConfig.sources, "skill-library": true },
    distillation: { deep: true, automatic: false },
  } });
  await writeEnvironment({ paths, state: {
    ...emptyEnvironment, phase: "active", records: [record],
    dispositions: [{
      key: record.rule.key, scope: "global", inputFingerprint: recordFingerprint(record),
      status: "published", publishedAt: 1_000, reason: "Synthetic publication", destinations: ["native-context"],
    }],
  } });
  const integration = await installIntegration({ paths, agent: engine, scope: "global", cwd, managedConfigPath: null });
  return { root, home, cwd, paths, record, integration };
}

export function probeResponse(engine: NativeEngine): NativeEngineRun {
  return {
    engine, text: "PINEAPPLE_READY", sessionId: "synthetic", transcriptPath: null,
    structured: null, resolvedModel: "synthetic-model", costUsd: 0, durationMs: 1, turns: 1,
    isError: false, errorMessage: null, permissionDenials: [], actions: [],
    cliVersion: "synthetic-version", resumableSessionId: null, usage: null,
  };
}
