import type { IndexedEvent } from "../eventIndex";
import { getEventRepository } from "./origin";
import type { CorrectionSignal, RepositoryIdentity } from "./types";

function previousAgentAction(
  events: readonly IndexedEvent[],
): IndexedEvent | null {
  for (let position = events.length - 1; position >= 0; position -= 1) {
    const event = events[position];

    if (
      event &&
      (event.kind === "tool-call" ||
        event.kind === "plan-presented" ||
        event.kind === "question-asked" ||
        event.kind === "assistant-text")
    ) {
      return event;
    }
  }

  return null;
}

function interruptionCategory(event: IndexedEvent | null): {
  readonly category: string;
  readonly label: string;
} {
  if (event?.tool) {
    return {
      category: `tool:${event.tool.name}`,
      label: `while using ${event.tool.name}`,
    };
  }

  if (event?.kind === "plan-presented") {
    return { category: "after-plan", label: "after presenting a plan" };
  }

  if (event?.kind === "assistant-text") {
    return { category: "assistant-text", label: "during an explanation" };
  }

  return { category: "other", label: "before finishing a response" };
}

function createSignal(options: {
  readonly kind: CorrectionSignal["kind"];
  readonly category: string;
  readonly label: string;
  readonly event: IndexedEvent;
  readonly repository: RepositoryIdentity;
  readonly relatedEvent?: IndexedEvent | null;
}): CorrectionSignal {
  const relatedRef = options.relatedEvent?.textRef;

  return {
    kind: options.kind,
    category: options.category,
    label: options.label,
    sessionId: options.event.sessionId,
    timestamp: options.event.timestamp,
    origin: options.repository.origin,
    repositoryName: options.repository.profileFileName,
    textRefs: options.event.textRef ? [options.event.textRef] : [],
    contextRefs: relatedRef ? [relatedRef] : [],
  };
}

function mineSession(options: {
  readonly events: readonly IndexedEvent[];
  readonly repositories: ReadonlyMap<string, RepositoryIdentity>;
}): readonly CorrectionSignal[] {
  const signals: CorrectionSignal[] = [];
  const history: IndexedEvent[] = [];
  let pendingQuestion: IndexedEvent | null = null;
  let pendingPlan: IndexedEvent | null = null;

  for (const event of options.events) {
    const repository = getEventRepository({
      event,
      repositories: options.repositories,
    });

    if (event.kind === "interruption") {
      const preceding = previousAgentAction(history);
      const category = interruptionCategory(preceding);

      signals.push(
        createSignal({
          kind: "interruption",
          ...category,
          event,
          repository,
          relatedEvent: preceding,
        }),
      );
    }

    if (event.kind === "permission-denied") {
      const preceding = previousAgentAction(history);
      const toolName = preceding?.tool?.name ?? "an unspecified tool";

      signals.push(
        createSignal({
          kind: "permission-denied",
          category: `tool:${toolName}`,
          label: toolName,
          event,
          repository,
          relatedEvent: preceding,
        }),
      );
    }

    if (event.kind === "question-asked") {
      pendingQuestion = event;
    }

    if (event.kind === "plan-presented") {
      pendingPlan = event;
    }

    if (event.kind === "user-prompt" || event.kind === "question-answered") {
      if (pendingQuestion !== null || event.kind === "question-answered") {
        signals.push(
          createSignal({
            kind: "question-answered",
            category: "agent-question",
            label: "an agent question",
            event,
            repository,
            relatedEvent: pendingQuestion,
          }),
        );
        pendingQuestion = null;
      }
    }

    if (event.kind === "user-prompt" || event.kind === "plan-resolved") {
      if (pendingPlan !== null || event.kind === "plan-resolved") {
        signals.push(
          createSignal({
            kind: "plan-resolved",
            category: "presented-plan",
            label: "a presented plan",
            event,
            repository,
            relatedEvent: pendingPlan,
          }),
        );
        pendingPlan = null;
      }
    }

    history.push(event);
  }

  return signals;
}

export function mineCorrections(options: {
  readonly events: readonly IndexedEvent[];
  readonly repositories: ReadonlyMap<string, RepositoryIdentity>;
}): readonly CorrectionSignal[] {
  const sessions = Map.groupBy(
    options.events,
    (event) => `${event.source}:${event.sessionId}`,
  );

  return [...sessions.values()].flatMap((events) =>
    mineSession({ events, repositories: options.repositories }),
  );
}
