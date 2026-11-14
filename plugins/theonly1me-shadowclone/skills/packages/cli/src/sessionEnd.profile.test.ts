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
import { openEventIndex, resolveCwdOrigin } from "@shadowclone/sessions";
import { profileRulePath, type ProfileRule } from "@shadowclone/profile";
import { runSessionEndHook } from "./hooks";
import { writeProfile } from "@shadowclone/environment";

test("session end recompiles existing guidance without creating advice", async () => {
  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-session-profile-"),
  );
  const paths = createProjectPaths({ homeDirectory, platform: "darwin" });
  const transcriptDirectory = path.join(
    paths.claudeProjectsDirectory,
    "fixture",
  );

  await mkdir(transcriptDirectory, { recursive: true });

  const sourcePath = path.join(transcriptDirectory, "session.jsonl");
  const records = [
    {
      type: "assistant",
      sessionId: "session",
      uuid: "event-1",
      timestamp: "2026-09-09T08:00:00.000Z",
      cwd: homeDirectory,
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
      cwd: homeDirectory,
      message: { id: "message-2", content: "[Request interrupted by user]" },
    },
  ];

  await Bun.write(
    sourcePath,
    `${records.map((record) => JSON.stringify(record)).join("\n")}\n`,
  );

  const config = setSourceEnabled({
    config: defaultConfig,
    source: "claude-code",
    enabled: true,
  });

  await writeConfig({ config, configPath: paths.configFile });

  const origin = await resolveCwdOrigin({
    cwd: homeDirectory,
    enabled: false,
  });
  const rule: ProfileRule = {
    key: "declared-small-diff",
    title: "Keeps changes focused",
    body: "Change only what the task requires.",
    section: "workflow",
    scope: "org",
    originDirectory: origin.directoryName,
    repositoryName: null,
    source: "declared",
    status: "active",
    proposal: null,
    appliesWhen: [],
    evidence: { for: [], against: [] },
    observations: 0,
    lastSeen: "unknown",
    sessions: 0,
    origins: [origin.id],
    importReference: null,
  };

  await writeProfile({ paths, rules: [rule] });

  const rulePath = path.join(paths.profileDirectory, profileRulePath(rule));
  const profileBefore = await Bun.file(rulePath).text();
  const stateBefore = await Bun.file(paths.profileManifestFile).text();

  await runSessionEndHook({
    input: JSON.stringify({ transcript_path: sourcePath, cwd: homeDirectory }),
    configPath: paths.configFile,
    paths,
    managedConfigPath: null,
  });

  const compiled = await Bun.file(paths.compiledProfileFile).text();

  expect(compiled).toContain("Keeps changes focused");
  expect(compiled).not.toContain("Stops the agent while using Edit");
  expect(await Bun.file(rulePath).text()).toBe(profileBefore);
  expect(await Bun.file(paths.profileManifestFile).text()).toBe(stateBefore);

  const index = await openEventIndex(paths.indexDatabase);

  expect(index.countEvents()).toBe(2);

  index.close();
});
