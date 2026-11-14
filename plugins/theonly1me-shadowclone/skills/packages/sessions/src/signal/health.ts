import type { AgentEvent } from "../observe";

export type SourceMarkerHealth = {
  readonly source: string;
  readonly sessions: number;
  readonly interruptions: number;
  readonly denials: number;
  readonly isStale: boolean;
};

export function computeSourceHealth(
  events: readonly AgentEvent[],
): readonly SourceMarkerHealth[] {
  const bySource = new Map<
    string,
    {
      readonly sessions: Set<string>;
      interruptions: number;
      denials: number;
    }
  >();

  for (const event of events) {
    let entry = bySource.get(event.source);

    if (!entry) {
      entry = {
        sessions: new Set(),
        interruptions: 0,
        denials: 0,
      };
      bySource.set(event.source, entry);
    }

    entry.sessions.add(event.sessionId);

    if (event.kind === "interruption") {
      entry.interruptions += 1;
    } else if (event.kind === "permission-denied") {
      entry.denials += 1;
    }
  }

  const results: SourceMarkerHealth[] = [];

  for (const [source, data] of bySource.entries()) {
    const sessions = data.sessions.size;
    const isSubjectToMarkers = source === "claude-code" || source === "codex";
    const isStale =
      isSubjectToMarkers &&
      sessions >= 25 &&
      data.interruptions === 0 &&
      data.denials === 0;

    results.push({
      source,
      sessions,
      interruptions: data.interruptions,
      denials: data.denials,
      isStale,
    });
  }

  return results.sort((a, b) => a.source.localeCompare(b.source));
}

export function checkMarkerStaleness(
  events: readonly AgentEvent[],
): readonly string[] {
  const health = computeSourceHealth(events);
  const warnings: string[] = [];

  for (const item of health) {
    if (item.isStale) {
      warnings.push(
        `Source "${item.source}" has ${item.sessions} sessions with 0 interruptions and 0 tool denials. Marker patterns may be stale.`,
      );
    }
  }

  return warnings;
}
