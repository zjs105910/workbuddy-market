import { expect, test } from "bun:test";
import { mkdir, mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { defaultConfig, writeConfig, createProjectPaths } from "@shadowclone/core";
import { normalizeRemoteRepository } from "@shadowclone/sessions";
import {
  maximumReferenceBytes,
  parseReference,
  readScopedReferences,
  recallReferences,
  referenceRelativePath,
  renderReference,
  searchReferences,
  type ReferenceRecord,
} from "./index";

const remote = "git@github.com:acme/sample-app.git";

function record(options: {
  readonly key: string;
  readonly title: string;
  readonly summary: string;
  readonly body: string;
}): ReferenceRecord {
  const repository = normalizeRemoteRepository(remote);

  if (repository?.profileFileName === null || repository === null) {
    throw new Error("Test remote must resolve");
  }

  return {
    schema: 1,
    ...options,
    tags: ["typescript", "testing"],
    scope: "project",
    originDirectory: repository.origin.directoryName,
    repositoryName: repository.profileFileName,
    source: "user",
    sourceLocator: `${options.key}.md`,
    updatedAt: "2026-09-18T00:00:00.000Z",
  };
}

test("reference Markdown round trips with strict metadata", () => {
  const reference = record({
    key: "retry-semantics",
    title: "Retry semantics",
    summary: "Retries use separate budgets.",
    body: "Failed and aborted attempts are counted separately.",
  });

  expect(parseReference(renderReference(reference))).toEqual(reference);
  expect(
    parseReference(
      renderReference(reference).replace("schema: 1", "extra: true"),
    ),
  ).toBeNull();
});

test("scoped reads exclude other repositories and malformed or oversized files", async () => {
  const home = await mkdtemp(path.join(os.tmpdir(), "shadowclone-references-"));
  const paths = createProjectPaths({ homeDirectory: home, platform: "darwin" });
  const repository = normalizeRemoteRepository(remote);

  if (repository?.profileFileName === null || repository === null) {
    throw new Error("Test remote must resolve");
  }

  const selected = record({
    key: "selected",
    title: "Selected",
    summary: "Current repository",
    body: "Use this.",
  });

  const selectedPath = path.join(
    paths.profileDirectory,
    referenceRelativePath(selected),
  );

  await mkdir(path.dirname(selectedPath), { recursive: true });
  await Bun.write(selectedPath, renderReference(selected));

  const otherPath = path.join(
    paths.profileDirectory,
    "references",
    "org",
    repository.origin.directoryName,
    "projects",
    "other-repository",
    "other.md",
  );

  await mkdir(path.dirname(otherPath), { recursive: true });
  await Bun.write(otherPath, "invalid");
  await Bun.write(
    path.join(path.dirname(selectedPath), "malformed.md"),
    "invalid",
  );
  await Bun.write(
    path.join(path.dirname(selectedPath), "oversized.md"),
    "x".repeat(maximumReferenceBytes + 1),
  );

  const results = await readScopedReferences({
    profileDirectory: paths.profileDirectory,
    origin: repository.origin,
    targetRepo: repository.profileFileName,
  });

  expect(results.map((result) => result.record.key)).toEqual(["selected"]);
});

test("search ranking is deterministic and recall redacts full records", async () => {
  const home = await mkdtemp(path.join(os.tmpdir(), "shadowclone-recall-"));
  const paths = createProjectPaths({ homeDirectory: home, platform: "darwin" });

  const exact = record({
    key: "retry",
    title: "Attempt handling",
    summary: "Queue behavior.",
    body: "Token sk_live_0123456789abcdefghij must not escape.",
  });

  const title = record({
    key: "attempts",
    title: "Retry guide",
    summary: "Retry details.",
    body: "More details.",
  });

  for (const reference of [title, exact]) {
    const target = path.join(
      paths.profileDirectory,
      referenceRelativePath(reference),
    );

    await mkdir(path.dirname(target), { recursive: true });
    await Bun.write(target, renderReference(reference));
  }

  await writeConfig({
    configPath: paths.configFile,
    config: {
      ...defaultConfig,
      sources: { ...defaultConfig.sources, "git-metadata": true },
    },
  });

  const scoped = await readScopedReferences({
    profileDirectory: paths.profileDirectory,
    origin: normalizeRemoteRepository(remote)?.origin ?? null,
    targetRepo: normalizeRemoteRepository(remote)?.profileFileName ?? null,
  });

  expect(
    searchReferences({ references: scoped, query: "retry", limit: 2 }).map(
      (result) => result.record.key,
    ),
  ).toEqual(["retry", "attempts"]);
  expect(
    searchReferences({
      references: scoped,
      query: "unrelated phrase",
      limit: 2,
    }),
  ).toEqual([]);

  const recalled = await recallReferences({
    query: "retry",
    limit: 2,
    cwd: home,
    paths,
    managedConfigPath: null,
    readRemote: async () => remote,
  });

  expect(recalled.records).toHaveLength(2);
  expect(recalled.records.join("\n")).toContain("[redacted:");
  expect(recalled.records.join("\n")).not.toContain(
    "sk_live_0123456789abcdefghij",
  );
});
