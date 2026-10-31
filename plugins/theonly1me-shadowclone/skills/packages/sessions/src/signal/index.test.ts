import { expect, test } from "bun:test";
import { signalCorpus, signalEvents } from "../testing";
import { deriveSignals, normalizeRemoteOrigin } from "./index";

test("normalizes a remote to its organization without credentials", () => {
  expect(
    normalizeRemoteOrigin("https://private-token@github.com/Acme/platform.git"),
  ).toEqual({
    id: "github.com/acme",
    directoryName: "github.com--acme--936913df4a5c268b",
    promotable: true,
  });
});

test("does not read git metadata without separate consent", async () => {
  let reads = 0;

  const derived = await deriveSignals({
    events: signalEvents,
    corpus: signalCorpus,
    gitMetadataEnabled: false,
    readRemote: () => {
      reads += 1;

      return Promise.resolve("git@github.com:acme/repo.git");
    },
  });

  expect(reads).toBe(0);
  expect(
    [...derived.origins.values()].every((origin) => !origin.promotable),
  ).toBeTrue();
});
