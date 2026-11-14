import { expect, test } from "bun:test";
import type { IndexedEvent } from "../eventIndex";
import type { RepositoryIdentity } from "./types";
import { mineSteeringEpisodes } from "./episodes";

const repository: RepositoryIdentity = {
  id: "local",
  name: null,
  profileFileName: null,
  origin: { id: "local", directoryName: "local", promotable: false },
};

const repositories = new Map([["/repo", repository]]);

function event(options: {
  readonly id: number;
  readonly kind: IndexedEvent["kind"];
  readonly sessionId?: string;
}): IndexedEvent {
  return {
    id: options.id,
    source: "claude-code",
    sourcePath: "/fixture.jsonl",
    eventId: `event-${options.id}`,
    sessionId: options.sessionId ?? "session-one",
    parentEventId: null,
    timestamp: options.id,
    cwd: "/repo",
    gitBranch: null,
    kind: options.kind,
    tool: null,
    isError: false,
    textRef: ["user-prompt", "assistant-text"].includes(options.kind)
      ? {
          type: "file",
          sourcePath: "/fixture.jsonl",
          byteOffset: options.id,
          byteLength: 1,
        }
      : null,
  };
}

test("bare stops and denials supply no preference evidence", () => {
  const events = [
    event({ id: 1, kind: "assistant-text" }),
    event({ id: 2, kind: "interruption" }),
    event({ id: 3, kind: "permission-denied" }),
  ];

  expect(mineSteeringEpisodes({ events, repositories })).toEqual([]);
});

test("back-to-back messages separated by a stop remain one steering episode", () => {
  const events = [
    event({ id: 1, kind: "assistant-text" }),
    event({ id: 2, kind: "user-prompt" }),
    event({ id: 3, kind: "interruption" }),
    event({ id: 4, kind: "user-prompt" }),
    event({ id: 5, kind: "tool-call" }),
    event({ id: 6, kind: "user-prompt" }),
  ];

  const episodes = mineSteeringEpisodes({ events, repositories });

  expect(episodes).toHaveLength(2);
  expect(episodes[0]?.textRefs).toHaveLength(2);
  expect(episodes[0]?.contextRefs).toHaveLength(1);
  expect(episodes[0]?.contextRefs?.[0]).toEqual(
    events[0]?.textRef ?? undefined,
  );
  expect(episodes[1]?.contextRefs).toEqual([]);
});

test("separate source sessions cannot become a single episode", () => {
  const first = event({ id: 1, kind: "user-prompt" });
  const second = {
    ...event({ id: 2, kind: "user-prompt" }),
    source: "codex" as const,
  };

  expect(
    mineSteeringEpisodes({ events: [first, second], repositories }).map(
      (episode) => episode.sessionId,
    ),
  ).toEqual(["claude-code:session-one", "codex:session-one"]);
});

test("Claude prompt history and its transcript count as one independent session", () => {
  const transcript = event({ id: 1, kind: "user-prompt" });
  const history = {
    ...event({ id: 2, kind: "user-prompt" }),
    source: "claude-prompts" as const,
  };
  const episodes = mineSteeringEpisodes({
    events: [transcript, history],
    repositories,
  });

  expect(episodes).toHaveLength(2);
  expect(new Set(episodes.map((episode) => episode.sessionId)).size).toBe(1);
});
