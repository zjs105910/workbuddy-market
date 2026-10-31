import { expect, test } from "bun:test";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { defaultConfig, writeConfig } from "@shadowclone/core";
import { openEventIndex } from "@shadowclone/sessions";
import { renderProfileRule, type ProfileRule } from "@shadowclone/profile";
import { referenceRelativePath, renderReference } from "@shadowclone/profile";
import { integrationFixture } from "@shadowclone/core/testing";
import { nativeSessionStart } from "./hooks";
import { installIntegration } from "./install";

test("main hooks point to reference recall without listing references, and subagents get neither", async () => {
  const fixture = await integrationFixture();
  const imported: ProfileRule = {
    key: "imported-repository-guidance",
    title: "Duplicated repository instruction",
    body: "This instruction already arrived through the repository.",
    section: "workflow",
    scope: "global",
    originDirectory: null,
    repositoryName: null,
    source: "imported",
    status: "active",
    proposal: null,
    appliesWhen: [],
    evidence: { for: [], against: [] },
    observations: 0,
    lastSeen: "imported",
    sessions: 0,
    origins: [],
    importReference: null,
  };

  await Bun.write(
    path.join(fixture.paths.profileDirectory, "global", "workflow.md"),
    `${renderProfileRule(imported)}\n`,
  );

  const reference = {
    schema: 1 as const,
    key: "queue-retries",
    title: "Queue retries",
    summary: "Queue retries use a separate budget.",
    tags: ["queue"],
    scope: "global" as const,
    originDirectory: null,
    repositoryName: null,
    source: "user" as const,
    sourceLocator: "queue.md",
    updatedAt: "2026-09-18",
    body: "Full retry details.",
  };
  const referencePath = path.join(
    fixture.paths.profileDirectory,
    referenceRelativePath(reference),
  );

  await mkdir(path.dirname(referencePath), { recursive: true });
  await Bun.write(referencePath, renderReference(reference));

  const installed = await installIntegration({
    ...fixture,
    agent: "claude-code",
    scope: "repository",
  });
  const main = await nativeSessionStart({
    ...fixture,
    id: installed.id,
    input: JSON.stringify({
      cwd: fixture.cwd,
      session_id: "main-session",
      hook_event_name: "SessionStart",
    }),
  });
  const subagent = await nativeSessionStart({
    ...fixture,
    id: installed.id,
    input: JSON.stringify({
      cwd: fixture.cwd,
      session_id: "subagent-session",
      hook_event_name: "SubagentStart",
    }),
  });

  expect(JSON.stringify(main)).toContain("shadowclone recall <query>");
  expect(JSON.stringify(main)).not.toContain("queue-retries");
  expect(JSON.stringify(main)).not.toContain(
    "Duplicated repository instruction",
  );
  expect(JSON.stringify(subagent)).not.toContain("shadowclone recall");
  expect(JSON.stringify(subagent)).not.toContain("queue-retries");
  expect(JSON.stringify(subagent)).not.toContain(
    "Duplicated repository instruction",
  );
  expect(JSON.stringify(subagent)).toContain("Use complete names.");
});

test("native hooks preserve repository attribution before a worktree disappears", async () => {
  const fixture = await integrationFixture();

  await writeConfig({
    configPath: fixture.paths.configFile,
    config: {
      ...defaultConfig,
      sources: { ...defaultConfig.sources, "git-metadata": true },
    },
  });

  const installed = await installIntegration({
    ...fixture,
    agent: "claude-code",
    scope: "repository",
  });

  await nativeSessionStart({
    ...fixture,
    id: installed.id,
    readRemote: async () => "git@github.com:acme/sample-app.git",
    input: JSON.stringify({
      cwd: fixture.cwd,
      session_id: "native-session",
      timestamp: 1_789_689_600_000,
      hook_event_name: "SessionStart",
    }),
  });

  const index = await openEventIndex(fixture.paths.indexDatabase);

  expect(
    index.getSessionOriginBinding({
      source: "claude-code",
      sessionId: "native-session",
      timestamp: 1_789_689_600_000,
    })?.id,
  ).toBe("github.com/acme/sample-app");

  index.close();
});
