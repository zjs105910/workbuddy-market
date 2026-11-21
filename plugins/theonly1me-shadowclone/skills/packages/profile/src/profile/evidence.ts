const explicitPrefix = "explicit:";

export function explicitProfileEvidence(evidenceId: string): string {
  return evidenceId.startsWith(explicitPrefix)
    ? evidenceId
    : `${explicitPrefix}${evidenceId}`;
}

export function isExplicitProfileEvidence(evidenceId: string): boolean {
  return evidenceId.startsWith(explicitPrefix);
}

export const independentSessionThreshold = 3;

export function activatesFromSessions(sessions: number): boolean {
  return sessions >= independentSessionThreshold;
}

export function effectiveProfileStatus(options: {
  readonly status: ProfileStatus;
  readonly evidence: ProfileEvidence;
}): ProfileStatus {
  return options.status === "candidate" &&
    options.evidence.for.some(isExplicitProfileEvidence)
    ? "active"
    : options.status;
}

export function profileEvidenceId(options: {
  readonly originId: string;
  readonly sessionId: string;
  readonly timestamp: number;
  readonly kind: string;
  readonly category: string;
}): string {
  return `signal:${JSON.stringify([
    options.originId,
    options.sessionId,
    options.timestamp,
    options.kind,
    options.category,
  ])}`;
}

export type ProfileEvidenceMoment = {
  readonly originId: string;
  readonly sessionId: string;
  readonly timestamp: number;
};

export function parseProfileEvidenceId(
  evidenceId: string,
): ProfileEvidenceMoment | null {
  const normalized = evidenceId.startsWith(explicitPrefix)
    ? evidenceId.slice(explicitPrefix.length)
    : evidenceId;

  if (!normalized.startsWith("signal:")) {
    return null;
  }

  let value: unknown;

  try {
    value = JSON.parse(normalized.slice("signal:".length));
  } catch {
    return null;
  }

  if (
    !Array.isArray(value) ||
    value.length !== 5 ||
    typeof value[0] !== "string" ||
    typeof value[1] !== "string" ||
    typeof value[2] !== "number"
  ) {
    return null;
  }

  return {
    originId: value[0],
    sessionId: value[1],
    timestamp: value[2],
  };
}

export function profileEvidenceStatistics(options: {
  readonly rule: ProfileRule;
  readonly evidence: ProfileEvidence;
}): Pick<ProfileRule, "observations" | "sessions" | "origins" | "lastSeen"> {
  const identifiers = [...options.evidence.for, ...options.evidence.against];
  const moments = identifiers.flatMap((identifier) => {
    const parsed = parseProfileEvidenceId(identifier);

    return parsed ? [parsed] : [];
  });
  const sessions = new Set(
    moments.map((moment) => `${moment.originId}\u0000${moment.sessionId}`),
  ).size;
  const hasUnresolvedHistory =
    moments.length !== identifiers.length ||
    (identifiers.length === 0 && options.rule.observations > 0);
  const resolvedOrigins = moments.map((moment) => moment.originId);

  const origins = [
    ...new Set(
      hasUnresolvedHistory
        ? [...options.rule.origins, ...resolvedOrigins]
        : resolvedOrigins,
    ),
  ].sort();

  const latestTimestamp = Math.max(
    0,
    ...moments.map((moment) => moment.timestamp),
  );
  const priorTimestamp = Date.parse(options.rule.lastSeen);
  const retainedTimestamp =
    hasUnresolvedHistory && Number.isFinite(priorTimestamp)
      ? priorTimestamp
      : 0;
  const lastTimestamp = Math.max(latestTimestamp, retainedTimestamp);

  return {
    observations: hasUnresolvedHistory
      ? Math.max(options.rule.observations, identifiers.length)
      : identifiers.length,
    sessions: hasUnresolvedHistory
      ? Math.max(options.rule.sessions, sessions)
      : sessions,
    origins,
    lastSeen:
      lastTimestamp > 0
        ? new Date(lastTimestamp).toISOString().slice(0, 10)
        : options.rule.lastSeen,
  };
}

import type { ProfileEvidence, ProfileRule, ProfileStatus } from "./types";
