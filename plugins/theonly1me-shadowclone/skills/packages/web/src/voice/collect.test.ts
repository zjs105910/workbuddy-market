import { expect, test } from "bun:test";
import { buildFixture } from "@shadowclone/builds/testing";
import { defaultConfig, setSourceEnabled, writeConfig } from "@shadowclone/core";
import { collectWriting } from "./collect";
import { fakeGitHub, keptCommit, keptPullRequest, keptReview, syntheticToken } from "./fixtures";

async function context(options: { readonly consent: boolean }) {
  const fixture = await buildFixture();

  await writeConfig({
    configPath: fixture.paths.configFile,
    config: setSourceEnabled({ config: defaultConfig, source: "github-writing", enabled: options.consent }),
  });

  return fixture;
}

test("with consent off, collection makes no gh call", async () => {
  const fixture = await context({ consent: false });
  const github = fakeGitHub();

  await expect(collectWriting({ ...fixture, run: github.run })).rejects.toThrow(
    "Allow Shadowclone to read your GitHub writing before you capture your voice",
  );
  expect(github.calls).toEqual([]);
});

test("collection keeps the user's own writing and skips agent, release, and merge text", async () => {
  const fixture = await context({ consent: true });
  const github = fakeGitHub();
  const writing = await collectWriting({ ...fixture, run: github.run });

  expect(github.calls.map((call) => call.slice(0, 3))).toEqual([
    ["gh", "api", "graphql"],
    ["gh", "search", "commits"],
  ]);
  expect(github.calls[1]).toContain("synthetic-writer");
  expect(writing.map((entry) => entry.kind)).toEqual(["pull-request", "review", "commit", "pull-request", "review"]);
  expect(writing.map((entry) => entry.text)).toContain(keptPullRequest);
  expect(writing.map((entry) => entry.text)).toContain(keptReview);
  expect(writing.map((entry) => entry.text)).toContain(keptCommit);

  const all = writing.map((entry) => entry.text).join("\n");

  for (const skipped of ["Add the sync command", "Tidy the parser", "release 1.4.0", "Merge pull request", "add the queue", "const secret"]) {
    expect(all).not.toContain(skipped);
  }
});

test("collection redacts secrets in the user's writing", async () => {
  const fixture = await context({ consent: true });
  const writing = await collectWriting({ ...fixture, run: fakeGitHub().run });
  const all = writing.map((entry) => entry.text).join("\n");

  expect(all).not.toContain(syntheticToken);
  expect(all).toContain("[redacted:github-token]");
});
