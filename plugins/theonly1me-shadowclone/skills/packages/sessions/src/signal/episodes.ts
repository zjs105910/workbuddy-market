import type { IndexedEvent } from "../eventIndex";
import { getEventRepository } from "./origin";
import type { CorrectionSignal, RepositoryIdentity } from "./types";
import { minePiEpisodes } from "./piEpisodes";

export function mineSteeringEpisodes(options: {
  readonly events: readonly IndexedEvent[];
  readonly repositories: ReadonlyMap<string, RepositoryIdentity>;
}): readonly CorrectionSignal[] {
  const episodes: CorrectionSignal[] = [];
  const sessions = Map.groupBy(
    options.events,
    (event) => `${event.source}:${event.sessionId}:${event.cwd}`,
  );

  for (const session of sessions.values()) {
    if (session[0]?.source === "pi") {
      episodes.push(...minePiEpisodes({ events: session, repositories: options.repositories }));
      continue;
    }
    let preceding: IndexedEvent | null = null;
    let prompts: IndexedEvent[] = [];

    const flush = () => {
      const first = prompts[0];
      const last = prompts.at(-1);

      if (!first || !last) {
        return;
      }

      const repository = getEventRepository({
        event: first,
        repositories: options.repositories,
      });

      episodes.push({
        kind: "user-steering",
        category: "user-episode",
        label: "user steering episode",
        sessionId: `${first.source === "claude-prompts" ? "claude-code" : first.source}:${first.sessionId}`,
        timestamp: last.timestamp,
        origin: repository.origin,
        repositoryName: repository.profileFileName,
        textRefs: prompts.flatMap((event) =>
          event.textRef ? [event.textRef] : [],
        ),
        contextRefs:
          preceding?.kind === "assistant-text" && preceding.textRef
            ? [preceding.textRef]
            : [],
      });
      prompts = [];
    };

    for (const event of [...session].sort(
      (left, right) => left.timestamp - right.timestamp || left.id - right.id,
    )) {
      if (
        (event.kind === "user-prompt" ||
          event.kind === "question-answered" ||
          event.kind === "plan-resolved") &&
        event.textRef
      ) {
        prompts.push(event);
      } else if (
        event.kind !== "interruption" &&
        event.kind !== "permission-denied"
      ) {
        flush();

        if (
          event.kind === "assistant-text" ||
          event.kind === "tool-call" ||
          event.kind === "session-end"
        ) {
          preceding = event;
        }
      }
    }

    flush();
  }

  return episodes.sort((left, right) => left.timestamp - right.timestamp);
}
