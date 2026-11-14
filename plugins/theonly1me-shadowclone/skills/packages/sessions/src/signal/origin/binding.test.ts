import { expect, test } from "bun:test";
import { Database } from "bun:sqlite";
import { createSchema } from "../../eventIndex/schema";
import { EventIndex } from "../../eventIndex/store";
import type { IndexedEvent } from "../../eventIndex";
import { eventOriginKey, resolveEventRepositories } from "./resolve";

function event(cwd: string): IndexedEvent {
  return {
    id: 1,
    sourcePath: "/transcripts/session.jsonl",
    source: "claude-code",
    sessionId: "session-one",
    eventId: "event-one",
    parentEventId: null,
    timestamp: Date.now(),
    cwd,
    gitBranch: null,
    kind: "user-prompt",
    tool: null,
    isError: false,
    textRef: null,
  };
}

function openIndex(): EventIndex {
  const database = new Database(":memory:", { create: true });

  createSchema(database);

  return new EventIndex(database);
}

test("a working directory keeps the owner it was first resolved under", async () => {
  const index = openIndex();
  const events = [event("/fixtures/sample-project")];

  const first = await resolveEventRepositories({
    events,
    enabled: true,
    readRemote: async () => "git@github.com:first-owner/sample-project.git",
    bindings: index,
  });

  const second = await resolveEventRepositories({
    events,
    enabled: true,
    readRemote: async () => "git@github.com:second-owner/sample-project.git",
    bindings: index,
  });

  expect(first.get(eventOriginKey(event("/fixtures/sample-project")))?.origin.id).toBe(
    "github.com/first-owner",
  );
  expect(second.get(eventOriginKey(event("/fixtures/sample-project")))?.origin.id).toBe(
    "github.com/first-owner",
  );

  index.close();
});

test("without a binding store the current remote wins every time", async () => {
  const events = [event("/fixtures/sample-project")];

  const second = await resolveEventRepositories({
    events,
    enabled: true,
    readRemote: async () => "git@github.com:second-owner/sample-project.git",
  });

  expect(second.get(eventOriginKey(event("/fixtures/sample-project")))?.origin.id).toBe(
    "github.com/second-owner",
  );
});

test("a binding is recorded the first time a directory resolves", async () => {
  const index = openIndex();

  expect(
    index.getOriginBinding(eventOriginKey(event("/fixtures/sample-project"))),
  ).toBeNull();

  await resolveEventRepositories({
    events: [event("/fixtures/sample-project")],
    enabled: true,
    readRemote: async () => "git@github.com:first-owner/sample-project.git",
    bindings: index,
  });

  expect(
    index.getOriginBinding(eventOriginKey(event("/fixtures/sample-project")))?.origin.id,
  ).toBe("github.com/first-owner");

  index.close();
});

test("disabled git metadata stays isolated without recording a permanent binding", async () => {
  const index = openIndex();
  const events = [event("/fixtures/sample-project")];

  const withoutConsent = await resolveEventRepositories({
    events,
    enabled: false,
    readRemote: async () => "git@github.com:owner/sample-project.git",
    bindings: index,
  });

  expect(
    withoutConsent.get(eventOriginKey(event("/fixtures/sample-project")))?.origin
      .promotable,
  ).toBeFalse();
  expect(
    index.getOriginBinding(eventOriginKey(event("/fixtures/sample-project"))),
  ).toBeNull();

  index.close();
});
