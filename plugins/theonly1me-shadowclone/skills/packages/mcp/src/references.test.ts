import { expect, test } from "bun:test";
import { mkdir, mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { defaultConfig, writeConfig, createProjectPaths } from "@shadowclone/core";
import { referenceRelativePath, renderReference } from "@shadowclone/profile";
import { normalizeRemoteRepository } from "@shadowclone/sessions";
import { runReferenceTool } from "./references";

test("MCP recall returns scoped full reference records", async () => {
  const home = await mkdtemp(path.join(os.tmpdir(), "shadowclone-mcp-recall-"));
  const paths = createProjectPaths({ homeDirectory: home, platform: "darwin" });
  const remote = "git@github.com:acme/sample-app.git";
  const repository = normalizeRemoteRepository(remote);

  if (repository?.profileFileName === null || repository === null) {
    throw new Error("Test remote must resolve");
  }

  const reference = {
    schema: 1 as const,
    key: "queue-retries",
    title: "Queue retries",
    summary: "Queue retry behavior.",
    tags: ["queue"],
    scope: "project" as const,
    originDirectory: repository.origin.directoryName,
    repositoryName: repository.profileFileName,
    source: "user" as const,
    sourceLocator: "queue.md",
    updatedAt: "2026-09-18",
    body: "Retry the queue five times.",
  };

  const target = path.join(
    paths.profileDirectory,
    referenceRelativePath(reference),
  );

  await mkdir(path.dirname(target), { recursive: true });
  await Bun.write(target, renderReference(reference));
  await writeConfig({
    configPath: paths.configFile,
    config: {
      ...defaultConfig,
      sources: { ...defaultConfig.sources, "git-metadata": true },
    },
  });

  const result = await runReferenceTool({
    params: {
      name: "shadowclone_recall",
      arguments: { query: "queue", limit: 1 },
    },
    paths,
    cwd: home,
    managedConfigPath: null,
    readRemote: async () => remote,
  });

  expect(result?.isError).toBeFalse();
  expect(result?.content[0]?.text).toContain("Retry the queue five times.");
  expect(result?.content[0]?.text).toContain('key: "queue-retries"');
});
