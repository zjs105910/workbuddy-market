import { expect, test } from "bun:test";
import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { defaultConfig, writeConfig, createProjectPaths } from "@shadowclone/core";
import type { IndexedEvent, CorrectionSignal } from "@shadowclone/sessions";
import { explicitProfileEvidence, profileEvidenceId, type ProfileRule } from "@shadowclone/profile";
import { queuePendingLearning, readPendingLearning, updatePendingLearning } from "./pending";
import { decidePendingLearning } from "./review";

async function fixture() {
  const paths = createProjectPaths({
    homeDirectory: await mkdtemp(path.join(os.tmpdir(), "shadowclone-pending-consent-")),
    platform: "darwin",
  });
  const config = {
    ...defaultConfig,
    sources: { ...defaultConfig.sources, codex: true },
    distillation: { deep: true, automatic: false },
  };
  await writeConfig({ configPath: paths.configFile, config });
  const signal: CorrectionSignal = {
    kind: "user-steering",
    category: "user-episode",
    label: "user steering episode",
    sessionId: "codex:synthetic-session",
    timestamp: 1_000,
    origin: { id: "synthetic", directoryName: "synthetic", promotable: false },
    repositoryName: null,
    textRefs: [{ type: "file", sourcePath: "/synthetic/session", byteOffset: 0, byteLength: 50 }],
  };
  const rule: ProfileRule = {
    key: "complete-names",
    title: "Use complete names",
    body: "Use complete variable names.",
    section: "engineering",
    source: "mined",
    status: "active",
    proposal: null,
    scope: "global",
    originDirectory: null,
    repositoryName: null,
    appliesWhen: [],
    evidence: {
      for: [explicitProfileEvidence(profileEvidenceId({
        originId: signal.origin.id,
        sessionId: signal.sessionId,
        timestamp: signal.timestamp,
        kind: signal.kind,
        category: signal.category,
      }))],
      against: [],
    },
    observations: 1,
    sessions: 1,
    origins: [signal.origin.id],
    lastSeen: "2026-09-05",
    importReference: null,
  };
  const event: IndexedEvent = {
    id: 1,
    source: "codex",
    sourcePath: "/synthetic/session",
    sessionId: "synthetic-session",
    eventId: "synthetic-event",
    parentEventId: null,
    timestamp: signal.timestamp,
    cwd: "/synthetic/repository",
    gitBranch: null,
    kind: "user-prompt",
    tool: null,
    isError: false,
    textRef: signal.textRefs[0] ?? null,
  };
  await queuePendingLearning({ paths, rules: [rule], signals: [signal], events: [event] });
  return { paths, config, rule };
}

test("a source disabled after learning blocks approval and keeps the rule pending", async () => {
  const { paths, config, rule } = await fixture();
  await writeConfig({
    configPath: paths.configFile,
    config: { ...config, sources: { ...config.sources, codex: false } },
  });
  await expect(decidePendingLearning({ paths, key: rule.key, action: "apply", managedConfigPath: null }))
    .rejects.toThrow("disabled sources: codex");
  expect((await readPendingLearning(paths)).rules).toHaveLength(1);
  expect(await Bun.file(path.join(paths.profileDirectory, "global", "engineering.md")).exists()).toBeFalse();

  await decidePendingLearning({ paths, key: rule.key, action: "reject", managedConfigPath: null });
  expect((await readPendingLearning(paths)).rules).toHaveLength(0);
});

test("approval needs complete provenance and current learning consent", async () => {
  const { paths, config, rule } = await fixture();
  await updatePendingLearning({ paths, update: (state) => ({ ...state, provenance: {} }) });
  await expect(decidePendingLearning({ paths, key: rule.key, action: "apply", managedConfigPath: null }))
    .rejects.toThrow("unresolved source provenance");
  await writeConfig({
    configPath: paths.configFile,
    config: { ...config, distillation: { deep: false, automatic: false } },
  });
  await expect(decidePendingLearning({ paths, key: rule.key, action: "apply", managedConfigPath: null }))
    .rejects.toThrow("Enable learning consent");
  expect((await readPendingLearning(paths)).rules).toHaveLength(1);
});
