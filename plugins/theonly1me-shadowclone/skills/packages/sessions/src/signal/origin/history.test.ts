import { expect, test } from "bun:test";
import { Database } from "bun:sqlite";
import { createSchema } from "../../eventIndex/schema";
import { EventIndex } from "../../eventIndex/store";
import type { IndexedEvent } from "../../eventIndex";
import { eventOriginKey, resolveEventRepositories } from "./resolve";

test("unknown history stays isolated and observed bindings survive schema rebuilding", async () => {
  const database = new Database(":memory:");

  createSchema(database);

  const index = new EventIndex(database);
  let reads = 0;
  const readRemote = async () => {
    reads += 1;

    return "https://github.com/example/project";
  };

  const event: IndexedEvent = {
    id: 1,
    source: "claude-code",
    sourcePath: "/capture/session",
    sessionId: "old",
    eventId: "one",
    parentEventId: null,
    timestamp: 1,
    cwd: "/project",
    gitBranch: null,
    kind: "user-prompt",
    tool: null,
    isError: false,
    textRef: null,
  };

  try {
    const historical = await resolveEventRepositories({
      events: [event],
      enabled: true,
      bindings: index,
      readRemote,
    });

    expect(
      historical.get(eventOriginKey(event))?.origin.promotable,
    ).toBeFalse();
    expect(reads).toBe(0);

    const observed = {
      ...event,
      timestamp: index.getOriginObservationStart(),
      sessionId: "current",
    };

    await resolveEventRepositories({
      events: [observed],
      enabled: true,
      bindings: index,
      readRemote,
    });

    expect(reads).toBe(1);

    database.exec("PRAGMA user_version = 0");
    createSchema(database);

    const rebuilt = await resolveEventRepositories({
      events: [observed],
      enabled: true,
      bindings: index,
      readRemote,
    });

    expect(rebuilt.get(eventOriginKey(observed))?.origin.id).toBe(
      "github.com/example",
    );
    expect(reads).toBe(1);
  } finally {
    index.close();
  }
});
