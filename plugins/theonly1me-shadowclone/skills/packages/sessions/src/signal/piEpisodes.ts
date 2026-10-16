import type { IndexedEvent } from "../eventIndex";
import { getEventRepository } from "./origin";
import type { CorrectionSignal, RepositoryIdentity } from "./types";

export function minePiEpisodes(options: {
  readonly events: readonly IndexedEvent[];
  readonly repositories: ReadonlyMap<string, RepositoryIdentity>;
}): readonly CorrectionSignal[] {
  const ancestors = new Map(options.events.map(event => [event.eventId, event]));
  return options.events.flatMap(event => {
    if (event.kind !== "user-prompt" || !event.textRef) return [];
    const repository = getEventRepository({ event, repositories: options.repositories });
    let parent = event.parentEventId;
    let preceding: IndexedEvent | undefined;
    const seen = new Set<string>();
    while (parent !== null && !seen.has(parent)) {
      seen.add(parent);
      preceding = ancestors.get(parent);
      if (!preceding || preceding.sessionId !== event.sessionId || preceding.cwd !== event.cwd ||
        preceding.kind === "user-prompt" || preceding.kind === "assistant-text") break;
      parent = preceding.parentEventId;
    }
    return [{
      kind: "user-steering" as const, category: "user-episode", label: "user steering episode",
      sessionId: `pi:${event.sessionId}`, timestamp: event.timestamp,
      origin: repository.origin, repositoryName: repository.profileFileName,
      textRefs: [event.textRef],
      contextRefs: preceding?.kind === "assistant-text" && preceding.textRef ? [preceding.textRef] : [],
    }];
  });
}
