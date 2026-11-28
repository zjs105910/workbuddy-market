import { expect, test } from "bun:test";
import { rm } from "node:fs/promises";
import { defaultConfig, writeConfig } from "@shadowclone/core";
import { readEnvironment } from "@shadowclone/environment";
import { acknowledgeCorrections, recordLaterCorrections, correctionReviewSignals } from "./feedback";
import { probeFixture } from "./probe.fixtures";

test("only later corrections to published guidance raise deduplicated review signals", async () => {
  const setup = await probeFixture("codex");
  try {
    await writeConfig({ configPath: setup.paths.configFile, config: {
      ...defaultConfig, sources: { ...defaultConfig.sources, codex: true },
    } });
    const state = await readEnvironment(setup.paths);
    const corrections = [
      { key: setup.record.rule.key, evidenceId: "after-publication", timestamp: 2_000, sessionId: "codex:synthetic" },
      { key: setup.record.rule.key, evidenceId: "before-publication", timestamp: 500, sessionId: "codex:synthetic" },
      { key: "unpublished", evidenceId: "unpublished", timestamp: 2_000, sessionId: "codex:synthetic" },
      { key: setup.record.rule.key, evidenceId: "revoked", timestamp: 2_000, sessionId: "claude-code:synthetic" },
    ];
    await recordLaterCorrections({ paths: setup.paths, state, corrections });
    await recordLaterCorrections({ paths: setup.paths, state, corrections });
    expect(await correctionReviewSignals(setup.paths)).toMatchObject([{ key: setup.record.rule.key, count: 1, lastCorrectionAt: 2_000 }]);
    expect(await readEnvironment(setup.paths)).toEqual(state);
    await acknowledgeCorrections({ paths: setup.paths, key: setup.record.rule.key });
    await recordLaterCorrections({ paths: setup.paths, state, corrections });
    expect(await correctionReviewSignals(setup.paths)).toEqual([]);
    await writeConfig({ configPath: setup.paths.configFile, config: defaultConfig });
    expect(await correctionReviewSignals(setup.paths)).toEqual([]);
  } finally {
    await rm(setup.root, { recursive: true, force: true });
  }
});
