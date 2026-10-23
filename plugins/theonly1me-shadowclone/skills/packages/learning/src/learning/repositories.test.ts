import { expect, test } from "bun:test";
import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import type { IndexedEvent } from "@shadowclone/sessions";
import {
  openEventIndex,
  deriveSignals,
  getEventRepository,
  resolveEventRepositories,
} from "@shadowclone/sessions";
import { createProjectPaths } from "@shadowclone/core";
import { episodeId, readLearningState, selectLearningEpisodes, writeLearningState } from "./state";
import { bindHistoricalRepository, listHistoricalRepositories } from "./repositories";

const event: IndexedEvent = {
  id: 1,
  sourcePath: "/synthetic/session.jsonl",
  source: "claude-code",
  sessionId: "synthetic-session",
  eventId: "event-1",
  parentEventId: null,
  timestamp: 1_000,
  cwd: "/synthetic/repository",
  gitBranch: null,
  kind: "user-prompt",
  tool: null,
  isError: false,
  textRef: null,
};

test("historical sessions stay isolated until a verified candidate is bound", async () => {
  const paths = createProjectPaths({
    homeDirectory: await mkdtemp(path.join(os.tmpdir(), "shadowclone-history-")),
    platform: "darwin",
  });
  const index = await openEventIndex(":memory:");
  const readRemote = async () => "git@github.com:acme/repository.git";
  const before = await resolveEventRepositories({
    events: [event],
    enabled: true,
    bindings: index,
    readRemote,
  });
  expect(getEventRepository({ event, repositories: before }).origin.promotable).toBeFalse();

  const candidates = await listHistoricalRepositories({
    index,
    events: [event],
    blockedOrigins: [],
    readRemote,
  });
  expect(candidates).toHaveLength(1);
  expect(candidates[0]?.repository.id).toBe("github.com/acme/repository");

  const candidate = candidates[0];

  if (!candidate) {
    throw new Error("Synthetic candidate was not found");
  }

  await bindHistoricalRepository({ index, candidate, paths, events: [event] });
  const after = await resolveEventRepositories({
    events: [event],
    enabled: true,
    bindings: index,
    readRemote: async () => {
      throw new Error("A reviewed binding should not need a remote read");
    },
  });

  expect(getEventRepository({ event, repositories: after }).id).toBe("github.com/acme/repository");
  expect(await listHistoricalRepositories({ index, events: [event], blockedOrigins: [], readRemote })).toHaveLength(0);
  index.close();
});

test("binding history reopens its processed episodes and preserves unrelated ledger entries", async () => {
  const paths = createProjectPaths({
    homeDirectory: await mkdtemp(path.join(os.tmpdir(), "shadowclone-history-ledger-")),
    platform: "darwin",
  });
  const index = await openEventIndex(":memory:");
  const prompt = {
    ...event,
    textRef: {
      type: "file" as const,
      sourcePath: event.sourcePath,
      byteOffset: 0,
      byteLength: 100,
    },
  };
  const isolated = await deriveSignals({
    events: [prompt], corpus: index.getCorpusSummary(), gitMetadataEnabled: false,
  });
  const state = {
    ...await readLearningState(paths),
    processed: [
      ...isolated.learning.map((signal) => ({ id: episodeId(signal), timestamp: signal.timestamp })),
      { id: "unrelated-episode", timestamp: prompt.timestamp },
    ],
  };
  await writeLearningState({ paths, state });
  expect(selectLearningEpisodes({ signals: isolated.learning, state, now: 2_000 })).toHaveLength(0);
  const [candidate] = await listHistoricalRepositories({
    index, events: [prompt], blockedOrigins: [],
    readRemote: async () => "git@github.com:acme/repository.git",
  });

  if (!candidate) throw new Error("Expected a synthetic binding candidate");

  expect(await bindHistoricalRepository({ index, candidate, paths, events: [prompt] })).toBe(1);
  const after = await readLearningState(paths);
  expect(after.processed).toEqual([{ id: "unrelated-episode", timestamp: prompt.timestamp }]);
  expect(selectLearningEpisodes({ signals: isolated.learning, state: after, now: 2_000 })).toHaveLength(1);
  index.close();
});

test("historical binding omits blocked repositories", async () => {
  const index = await openEventIndex(":memory:");
  const candidates = await listHistoricalRepositories({
    index,
    events: [event],
    blockedOrigins: ["github.com/acme"],
    readRemote: async () => "git@github.com:acme/repository.git",
  });

  expect(candidates).toHaveLength(0);
  index.close();
});
