import { expect, test } from "bun:test";
import { Database } from "bun:sqlite";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { readConfig } from "@shadowclone/core";
import { allowlistedSignals, authorizedLearningEvents } from "@shadowclone/learning";
import {
  EventIndex,
  ingestSources,
  openEventIndex,
  observeClaudeCodeFile,
  resolveRedacted,
  deriveSignals,
  eventOriginKey,
  resolveEventRepositories,
} from "@shadowclone/sessions";
import { treeFingerprint } from "../../native/files";
import { correctionRepositoryHistory, correctionSessions } from "./corpus";
import { materializeCorpus, prepareManualEnvironment, reusableLayout } from "./environments";
import { validateCorpusScope, verifiedCorpusRepository } from "./corpusScope";

test("fixed correction history resolves to registered Atlas before learning and leaves unknown history isolated", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "v3-corpus-scope-"));
  try {
    await prepareManualEnvironment({ directory, arm: "deep-0", routed: true });
    await materializeCorpus({ directory, preparation: 0 });
    const paths = reusableLayout(directory).paths("deep-0");
    const before = await treeFingerprint(paths.shadowcloneDirectory);
    await expect(validateCorpusScope({ directory, preparation: 0 })).resolves.toMatchObject({
      sessions: correctionSessions.length,
      events: correctionSessions.reduce((total, session) => total + session.messages.length, 0),
      repository: "github.com/synthetic-shadowclone/atlas",
    });
    expect(await treeFingerprint(paths.shadowcloneDirectory)).toBe(before);
    const index = new EventIndex(new Database(paths.indexDatabase, { readonly: true }));
    try {
      const batch = await observeClaudeCodeFile({
        sourcePath: path.join(paths.claudeProjectsDirectory, "synthetic-atlas/atlas-api-new.jsonl"),
        cursor: null,
      });
      const event = batch?.events.find((event) => event.kind === "user-prompt");
      if (!event) throw new Error("Synthetic correction missing.");
      expect(event.timestamp).toBeLessThan(index.getOriginObservationStart());
      const unknown = {
        ...event,
        id: 1,
        sourcePath: "synthetic-history",
        sessionId: "unobserved-history",
      };
      const repositories = await resolveEventRepositories({
        events: [unknown],
        enabled: true,
        bindings: index,
      });
      expect(repositories.get(eventOriginKey(unknown))?.origin.promotable).toBe(false);
    } finally {
      index.close();
    }
    const database = new Database(paths.indexDatabase);
    try {
      database
        .query("DELETE FROM origin_binding_timeline WHERE session_id = ?")
        .run("atlas-api-new");
    } finally {
      database.close();
    }
    await expect(validateCorpusScope({ directory, preparation: 0 })).rejects.toThrow(
      "scope is unresolved",
    );
    await materializeCorpus({ directory, preparation: 0 });
    expect((await validateCorpusScope({ directory, preparation: 0 })).sessions).toBe(
      correctionRepositoryHistory.length,
    );
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
}, 30000);

test("real ingestion retains paired examples while excluding tool output and respecting source consent", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "v3-corpus-ingestion-"));
  try {
    await prepareManualEnvironment({ directory, arm: "deep-0", routed: true });
    await materializeCorpus({ directory, preparation: 0 });
    const paths = reusableLayout(directory).paths("deep-0");
    const config = await readConfig({ configPath: paths.configFile });
    const enabled = { ...config, sources: { ...config.sources, "claude-code": true } };
    const repository = await verifiedCorpusRepository({ directory, preparation: 0 });
    const index = await openEventIndex(paths.indexDatabase);
    try {
      expect((await ingestSources({ index, paths, config })).events).toBe(0);
      const summary = await ingestSources({ index, paths, config: enabled });
      expect(summary.invalidRecords).toBe(0);
      expect(summary.events).toBe(23);
      const events = index.listEvents();
      expect(authorizedLearningEvents({ events, config })).toHaveLength(0);
      const eligible = authorizedLearningEvents({ events, config: enabled });
      const signals = await deriveSignals({
        events: eligible,
        corpus: index.getCorpusSummary(),
        gitMetadataEnabled: true,
        bindings: index,
      });
      const episodes = allowlistedSignals({ signals: signals.learning, events: eligible });
      expect(episodes).toHaveLength(correctionSessions.length);
      for (const session of correctionSessions) {
        const episode = episodes.find((entry) => entry.sessionId === `claude-code:${session.id}`);
        expect(episode?.repositoryName).toBe(repository.profileFileName);
        expect(episode?.origin.promotable).toBe(true);
        expect(episode?.textRefs).toHaveLength(1);
        expect(episode?.contextRefs).toHaveLength(1);
        for (const ref of [...(episode?.textRefs ?? []), ...(episode?.contextRefs ?? [])]) {
          const text = await resolveRedacted({ ref, roots: [paths.claudeProjectsDirectory] });
          expect(text).not.toContain("always force push");
        }
      }
      expect(
        signals.learning.some((entry) => entry.sessionId.endsWith("excluded-tool-output")),
      ).toBe(false);
      expect((await ingestSources({ index, paths, config: enabled })).events).toBe(0);
    } finally {
      index.close();
    }
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
}, 30000);

test("fixture materialization refuses a changed synthetic remote", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "v3-corpus-remote-"));
  try {
    await prepareManualEnvironment({ directory, arm: "deep-0", routed: true });
    const layout = reusableLayout(directory);
    const configFile = path.join(
      layout.workspace({ arm: "deep-0", repository: "atlas" }),
      ".git/config",
    );
    await Bun.write(
      configFile,
      (await Bun.file(configFile).text()).replace(
        "synthetic-shadowclone/atlas.git",
        "synthetic-shadowclone/boreal.git",
      ),
    );
    await expect(materializeCorpus({ directory, preparation: 0 })).rejects.toThrow(
      "registered synthetic Atlas",
    );
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
}, 30000);
