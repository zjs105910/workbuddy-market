import path from "node:path";
import { fingerprint } from "@shadowclone/core";
import type {
  EventIndex,
  IndexedEvent,
  GitRemoteReader,
  RepositoryIdentity,
} from "@shadowclone/sessions";
import {
  isOriginBlocked,
  normalizeRemoteRepository,
  readGitRemote,
  deriveSignals,
  eventOriginKey,
} from "@shadowclone/sessions";
import type { ProjectPaths } from "@shadowclone/core";
import { episodeId, readLearningState, writeLearningState } from "./state";

export type HistoricalRepositoryCandidate = {
  readonly id: string;
  readonly directory: string;
  readonly repository: RepositoryIdentity;
  readonly sessionCount: number;
  readonly originKeys: readonly string[];
};

export async function listHistoricalRepositories(options: {
  readonly index: EventIndex;
  readonly events: readonly IndexedEvent[];
  readonly blockedOrigins: readonly string[];
  readonly readRemote?: GitRemoteReader;
}): Promise<readonly HistoricalRepositoryCandidate[]> {
  const observedSince = options.index.getOriginObservationStart();
  const groups = Map.groupBy(
    options.events.filter((event) =>
      event.cwd.length > 0 &&
      event.timestamp < observedSince &&
      options.index.getOriginBinding(eventOriginKey(event)) === null
    ),
    (event) => path.resolve(event.cwd),
  );
  const candidates: HistoricalRepositoryCandidate[] = [];

  for (const [directory, events] of groups) {
    const remote = await (options.readRemote ?? readGitRemote)(directory);
    const repository = remote === null ? null : normalizeRemoteRepository(remote);

    if (repository === null || isOriginBlocked({
      repository,
      patterns: options.blockedOrigins,
    })) {
      continue;
    }

    candidates.push({
      id: fingerprint(JSON.stringify([directory, repository.id])).slice(0, 16),
      directory,
      repository,
      sessionCount: new Set(events.map((event) => `${event.source}:${event.sessionId}`)).size,
      originKeys: [...new Set(events.map(eventOriginKey))],
    });
  }

  return candidates.sort((left, right) => left.directory.localeCompare(right.directory));
}

export async function bindHistoricalRepository(options: {
  readonly index: EventIndex;
  readonly candidate: HistoricalRepositoryCandidate;
  readonly paths: ProjectPaths;
  readonly events: readonly IndexedEvent[];
}): Promise<number> {
  const originKeys = new Set(options.candidate.originKeys);
  const derived = await deriveSignals({
    events: options.events.filter((event) => originKeys.has(eventOriginKey(event))),
    corpus: options.index.getCorpusSummary(),
    gitMetadataEnabled: false,
  });
  const affectedIds = new Set(derived.learning.map(episodeId));
  const state = await readLearningState(options.paths);
  const processed = state.processed.filter((entry) => !affectedIds.has(entry.id));
  const reconsidered = state.processed.length - processed.length;

  if (reconsidered > 0) {
    await writeLearningState({ paths: options.paths, state: { ...state, processed } });
  }

  for (const originKey of options.candidate.originKeys) {
    options.index.bindOrigin({ originKey, repository: options.candidate.repository });
  }

  return reconsidered;
}
