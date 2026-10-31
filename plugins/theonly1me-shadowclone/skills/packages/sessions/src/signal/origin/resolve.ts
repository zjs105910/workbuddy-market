import path from "node:path";
import type { IndexedEvent } from "../../eventIndex";
import type { OriginScope, RepositoryIdentity } from "../types";
import {
  isolatedOrigin,
  normalizeRemoteOrigin,
  normalizeRemoteRepository,
  readGitRemote,
} from "./remote";
import type { GitRemoteReader } from "./remote";

export function eventOriginKey(event: IndexedEvent): string {
  return JSON.stringify([
    event.source,
    event.sessionId,
    event.cwd ? path.resolve(event.cwd) : "",
    event.cwd ? null : event.timestamp,
  ]);
}

function eventIsolationKey(event: IndexedEvent): string {
  return JSON.stringify([
    event.source,
    event.sessionId,
    event.cwd ? path.resolve(event.cwd) : "",
  ]);
}

export async function resolveCwdOrigin(options: {
  readonly cwd: string;
  readonly fallbackKey?: string;
  readonly enabled: boolean;
  readonly readRemote?: GitRemoteReader;
}): Promise<OriginScope> {
  const key = options.cwd || options.fallbackKey || "unknown";
  const readRemote = options.readRemote ?? readGitRemote;
  const remote =
    options.enabled && options.cwd.length > 0
      ? await readRemote(options.cwd)
      : null;

  return remote === null
    ? isolatedOrigin(key)
    : (normalizeRemoteOrigin(remote) ?? isolatedOrigin(key));
}

export async function resolveRepository(options: {
  readonly cwd: string;
  readonly fallbackKey?: string;
  readonly enabled: boolean;
  readonly readRemote?: GitRemoteReader;
}): Promise<RepositoryIdentity> {
  const readRemote = options.readRemote ?? readGitRemote;
  const remote =
    options.enabled && options.cwd.length > 0
      ? await readRemote(options.cwd)
      : null;
  const repository = remote ? normalizeRemoteRepository(remote) : null;

  if (repository !== null) {
    return repository;
  }

  const origin = await resolveCwdOrigin({
    cwd: options.cwd,
    fallbackKey: options.fallbackKey,
    enabled: false,
  });

  return { id: origin.id, name: null, profileFileName: null, origin };
}

export type OriginBindingStore = {
  readonly getOriginObservationStart?: () => number;
  readonly getOriginBinding: (originKey: string) => RepositoryIdentity | null;
  readonly bindOrigin: (options: {
    readonly originKey: string;
    readonly repository: RepositoryIdentity;
  }) => void;
  readonly getSessionOriginBinding?: (options: {
    readonly source: string;
    readonly sessionId: string;
    readonly timestamp: number;
  }) => RepositoryIdentity | null;
};

export async function resolveEventRepositories(options: {
  readonly events: readonly IndexedEvent[];
  readonly enabled: boolean;
  readonly readRemote?: GitRemoteReader;
  readonly bindings?: OriginBindingStore;
}): Promise<ReadonlyMap<string, RepositoryIdentity>> {
  const repositories = new Map<string, RepositoryIdentity>();
  const readRemote = options.readRemote ?? readGitRemote;

  for (const event of options.events) {
    const key = eventOriginKey(event);

    if (repositories.has(key)) {
      continue;
    }

    const timeline = options.enabled
      ? (options.bindings?.getSessionOriginBinding?.({
          source: event.source,
          sessionId: event.sessionId,
          timestamp: event.timestamp,
        }) ?? null)
      : null;

    const bound =
      timeline ??
      (options.enabled && event.cwd.length > 0
        ? (options.bindings?.getOriginBinding(key) ?? null)
        : null);

    if (bound !== null) {
      repositories.set(key, bound);

      continue;
    }

    const observedSince = options.bindings?.getOriginObservationStart?.() ?? 0;
    const hasObservedHistory = event.timestamp >= observedSince;

    const resolved = await resolveRepository({
      cwd: event.cwd,
      fallbackKey: eventIsolationKey(event),
      enabled: options.enabled && hasObservedHistory,
      readRemote,
    });

    repositories.set(key, resolved);

    if (options.enabled && event.cwd.length > 0 && resolved.origin.promotable) {
      options.bindings?.bindOrigin({ originKey: key, repository: resolved });
    }
  }

  return repositories;
}

export function getEventRepository(options: {
  readonly event: IndexedEvent;
  readonly repositories: ReadonlyMap<string, RepositoryIdentity>;
}): RepositoryIdentity {
  const key = eventOriginKey(options.event);
  const known = options.repositories.get(key);

  if (known) {
    return known;
  }

  const origin = isolatedOrigin(eventIsolationKey(options.event));

  return { id: origin.id, name: null, profileFileName: null, origin };
}

export function getEventOrigin(options: {
  readonly event: IndexedEvent;
  readonly origins: ReadonlyMap<string, OriginScope>;
}): OriginScope {
  return (
    options.origins.get(eventOriginKey(options.event)) ??
    isolatedOrigin(eventIsolationKey(options.event))
  );
}
