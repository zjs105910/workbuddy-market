import { expect, test } from "bun:test";
import { normalizeRemoteOrigin } from "./remote";
import { resolveEventRepositories } from "./resolve";
import type { RepositoryIdentity } from "../types";
import type { OriginBindingStore } from "./resolve";
import type { IndexedEvent } from "../../eventIndex";

const event: IndexedEvent = {
  id: 1,
  sourcePath: "/sessions/one",
  source: "claude-code",
  sessionId: "one",
  eventId: "one",
  parentEventId: null,
  timestamp: 1,
  cwd: "/workspace",
  gitBranch: null,
  kind: "user-prompt",
  tool: null,
  isError: false,
  textRef: null,
};

test("namespace punctuation cannot collide in profile directories", () => {
  const nested = normalizeRemoteOrigin("https://example.com/team/sub/repo");
  const flat = normalizeRemoteOrigin("https://example.com/team--sub/repo");

  expect(nested?.directoryName).not.toBe(flat?.directoryName);
  expect(normalizeRemoteOrigin("https://example.com/%ZZ/repo")).toBeNull();
  expect(
    normalizeRemoteOrigin("https://example.com/team%2fsub/repo"),
  ).toBeNull();
  expect(normalizeRemoteOrigin("ssh://example.com/Team/repo")?.id).not.toBe(
    normalizeRemoteOrigin("ssh://example.com/team/repo")?.id,
  );
});

test("new sessions at a reused directory bind independently and disabled metadata never reads remotes", async () => {
  const bindings = new Map<string, RepositoryIdentity>();

  const store: OriginBindingStore = {
    getOriginBinding: (key) => bindings.get(key) ?? null,
    bindOrigin: ({ originKey, repository }) => {
      bindings.set(originKey, repository);
    },
  };

  let owner = "first";
  let reads = 0;
  const readRemote = async () => {
    reads += 1;

    return `https://github.com/${owner}/repo`;
  };

  const first = await resolveEventRepositories({
    events: [event],
    enabled: true,
    bindings: store,
    readRemote,
  });

  owner = "second";

  const disabled = await resolveEventRepositories({
    events: [event],
    enabled: false,
    bindings: store,
    readRemote,
  });

  expect([...disabled.values()][0]?.origin.promotable).toBeFalse();
  expect(reads).toBe(1);

  const second = await resolveEventRepositories({
    events: [{ ...event, sessionId: "two" }],
    enabled: true,
    bindings: store,
    readRemote,
  });

  expect([...first.values()][0]?.origin.id).toBe("github.com/first");
  expect([...second.values()][0]?.origin.id).toBe("github.com/second");
});
