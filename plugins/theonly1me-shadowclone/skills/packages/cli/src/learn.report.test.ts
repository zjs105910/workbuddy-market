import { expect, test } from "bun:test";
import { mkdir, mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import {
  defaultConfig,
  setSourceEnabled,
  writeConfig,
  createProjectPaths,
} from "@shadowclone/core";
import { openEventIndex } from "@shadowclone/sessions";
import type { ProfileRule } from "@shadowclone/profile";
import { learn } from "./learn";
import { writeProfile } from "@shadowclone/environment";

function declaredRule(): ProfileRule {
  return {
    key: "declared-plan-first",
    title: "Plans consequential changes",
    body: "Write a plan before changing architecture.",
    section: "workflow",
    scope: "global",
    originDirectory: null,
    repositoryName: null,
    source: "declared",
    status: "active",
    proposal: null,
    appliesWhen: [],
    evidence: { for: [], against: [] },
    observations: 0,
    lastSeen: "unknown",
    sessions: 0,
    origins: [],
    importReference: null,
  };
}

async function profileSnapshot(
  profileDirectory: string,
): Promise<Readonly<Record<string, string>>> {
  const relativePaths = await Array.fromAsync(
    new Bun.Glob("**/*").scan({
      cwd: profileDirectory,
      dot: true,
      onlyFiles: true,
    }),
  );
  const entries = await Promise.all(
    relativePaths
      .sort()
      .map(
        async (relativePath) =>
          [
            relativePath,
            await Bun.file(path.join(profileDirectory, relativePath)).text(),
          ] as const,
      ),
  );

  return Object.fromEntries(entries);
}

test("plain learn reports evidence without changing the profile", async () => {
  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-learn-report-"),
  );
  const paths = createProjectPaths({ homeDirectory, platform: "darwin" });
  const transcriptDirectory = path.join(
    paths.claudeProjectsDirectory,
    "fixture",
  );

  await mkdir(transcriptDirectory, { recursive: true });

  const records = [
    {
      type: "assistant",
      sessionId: "session",
      uuid: "event-1",
      timestamp: "2026-09-09T08:00:00.000Z",
      cwd: "/repo",
      message: {
        id: "message-1",
        content: [{ type: "tool_use", id: "tool-1", name: "Edit" }],
      },
    },
    {
      type: "user",
      sessionId: "session",
      uuid: "event-2",
      timestamp: "2026-09-09T08:01:00.000Z",
      cwd: "/repo",
      message: { id: "message-2", content: "[Request interrupted by user]" },
    },
  ];

  await Bun.write(
    path.join(transcriptDirectory, "session.jsonl"),
    `${records.map((record) => JSON.stringify(record)).join("\n")}\n`,
  );

  const config = setSourceEnabled({
    config: defaultConfig,
    source: "claude-code",
    enabled: true,
  });

  await writeConfig({ config, configPath: paths.configFile });
  await writeProfile({ paths, rules: [declaredRule()] });

  const before = await profileSnapshot(paths.profileDirectory);

  await learn({
    configPath: paths.configFile,
    databasePath: paths.indexDatabase,
    paths,
    managedConfigPath: null,
  });

  expect(await profileSnapshot(paths.profileDirectory)).toEqual(before);

  const index = await openEventIndex(paths.indexDatabase);

  expect(index.countEvents()).toBe(2);

  index.close();
});
