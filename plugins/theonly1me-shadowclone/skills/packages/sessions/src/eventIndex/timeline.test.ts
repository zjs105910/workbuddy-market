import { expect, test } from "bun:test";
import { mkdir, mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { defaultConfig, createProjectPaths } from "@shadowclone/core";
import type { IndexedEvent } from "./types";
import {
  getEventRepository,
  normalizeRemoteRepository,
  resolveEventRepositories,
} from "../signal";
import { ingestSources, openEventIndex } from "./index";

function event(options: {
  readonly id: number;
  readonly timestamp: number;
}): IndexedEvent {
  return {
    id: options.id,
    sourcePath: "/transcript",
    source: "antigravity",
    sessionId: "conversation",
    eventId: `event-${options.id}`,
    parentEventId: null,
    timestamp: options.timestamp,
    cwd: "",
    gitBranch: null,
    kind: "user-prompt",
    tool: null,
    isError: false,
    textRef: null,
  };
}

test("timeline bindings resolve a session that changes repositories", async () => {
  const index = await openEventIndex(":memory:");
  const first = normalizeRemoteRepository("git@github.com:acme/first.git");
  const second = normalizeRemoteRepository("git@github.com:acme/second.git");

  if (first === null || second === null) {
    throw new Error("Test remotes must resolve");
  }

  index.bindSessionOrigin({
    source: "antigravity",
    sessionId: "conversation",
    timestamp: 1_000,
    repository: first,
  });
  index.bindSessionOrigin({
    source: "antigravity",
    sessionId: "conversation",
    timestamp: 2_000,
    repository: second,
  });

  const events = [
    event({ id: 1, timestamp: 1_500 }),
    event({ id: 2, timestamp: 2_500 }),
  ];

  const repositories = await resolveEventRepositories({
    events,
    enabled: true,
    bindings: index,
    readRemote: async () => {
      throw new Error("Timeline lookup must not read a deleted workspace");
    },
  });

  expect(
    getEventRepository({
      event: events[0] ?? event({ id: 0, timestamp: 0 }),
      repositories,
    }).id,
  ).toBe(first.id);
  expect(
    getEventRepository({
      event: events[1] ?? event({ id: 0, timestamp: 0 }),
      repositories,
    }).id,
  ).toBe(second.id);

  index.close();
});

test("an unattributed session keeps one isolated identity across events", async () => {
  const index = await openEventIndex(":memory:");
  const events = [
    event({ id: 1, timestamp: 1_500 }),
    event({ id: 2, timestamp: 2_500 }),
  ];

  const repositories = await resolveEventRepositories({
    events,
    enabled: true,
    bindings: index,
  });

  expect(
    getEventRepository({
      event: events[0] ?? event({ id: 0, timestamp: 0 }),
      repositories,
    }).id,
  ).toBe(
    getEventRepository({
      event: events[1] ?? event({ id: 0, timestamp: 0 }),
      repositories,
    }).id,
  );

  index.close();
});

test("workspace history is unread while disabled and stores metadata only when enabled", async () => {
  const home = await mkdtemp(path.join(os.tmpdir(), "shadowclone-timeline-"));
  const paths = createProjectPaths({ homeDirectory: home, platform: "darwin" });

  await mkdir(path.dirname(paths.antigravityWorkspaceHistoryFile), {
    recursive: true,
  });

  const secretDisplay = "private display text that must not be indexed";

  await Bun.write(
    paths.antigravityWorkspaceHistoryFile,
    `${JSON.stringify({
      conversationId: "conversation",
      timestamp: 1_789_689_600_000,
      workspace: path.join(home, "first"),
      display: secretDisplay,
    })}\n${JSON.stringify({
      conversationId: "conversation",
      timestamp: 1_789_689_700_000,
      workspace: path.join(home, "second"),
      display: secretDisplay,
    })}\n`,
  );

  const index = await openEventIndex(paths.indexDatabase);
  const disabled = await ingestSources({ index, config: defaultConfig, paths });

  expect(disabled.files).toBe(0);
  expect(
    index.getSessionOriginBinding({
      source: "antigravity",
      sessionId: "conversation",
      timestamp: 1_789_689_750_000,
    }),
  ).toBeNull();

  const config = {
    ...defaultConfig,
    sources: {
      ...defaultConfig.sources,
      "antigravity-workspaces": true,
      "git-metadata": true,
    },
  };

  const enabled = await ingestSources({
    index,
    config,
    paths,
    readRemote: async (cwd) =>
      cwd.endsWith("first")
        ? "git@github.com:acme/first.git"
        : "git@github.com:acme/second.git",
  });

  expect(enabled.files).toBe(1);
  expect(index.listEvents()).toEqual([]);
  expect(
    index.getSessionOriginBinding({
      source: "antigravity",
      sessionId: "conversation",
      timestamp: 1_789_689_750_000,
    })?.id,
  ).toBe("github.com/acme/second");

  index.close();

  const databaseText = Buffer.from(
    await Bun.file(paths.indexDatabase).arrayBuffer(),
  ).toString("utf8");

  expect(databaseText).not.toContain(secretDisplay);
});
