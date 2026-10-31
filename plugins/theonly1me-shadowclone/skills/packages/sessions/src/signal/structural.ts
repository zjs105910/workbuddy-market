import type { IndexedEvent } from "../eventIndex";
import type { CountedCategory, StructuralSummary } from "./types";

function countCategories(
  values: readonly {
    readonly category: string;
    readonly label: string;
  }[],
): readonly CountedCategory[] {
  const counts = new Map<string, CountedCategory>();

  for (const value of values) {
    const existing = counts.get(value.category);

    counts.set(value.category, {
      ...value,
      count: (existing?.count ?? 0) + 1,
    });
  }

  return [...counts.values()].sort(
    (left, right) =>
      right.count - left.count || left.label.localeCompare(right.label),
  );
}

export function countSignals(
  values: readonly {
    readonly category: string;
    readonly label: string;
  }[],
): readonly CountedCategory[] {
  return countCategories(values);
}

export function deriveStructural(
  events: readonly IndexedEvent[],
): StructuralSummary {
  const sessions = new Set(
    events.map((event) => `${event.source}:${event.sessionId}`),
  );
  const planSessions = new Set(
    events
      .filter((event) => event.kind === "plan-presented")
      .map((event) => `${event.source}:${event.sessionId}`),
  );
  const toolUses = countCategories(
    events.flatMap((event) =>
      event.tool ? [{ category: event.tool.name, label: event.tool.name }] : [],
    ),
  );

  return {
    toolUses,
    planSessions: planSessions.size,
    totalSessions: sessions.size,
  };
}
