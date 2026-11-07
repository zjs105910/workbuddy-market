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
import { installIntegration, writeProfile } from "@shadowclone/environment";
import { checkoutRoot, integrationFixture } from "@shadowclone/core/testing";
import { getSessionStartContext, runSessionEndHook } from "./hooks";

test("the session hook does not inspect input for a disabled source", async () => {
  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-hook-"),
  );
  const paths = createProjectPaths({
    homeDirectory,
    platform: "darwin",
  });

  await writeConfig({ config: defaultConfig, configPath: paths.configFile });

  await expect(
    runSessionEndHook({
      input: "not json and not a path",
      configPath: paths.configFile,
      paths,
      managedConfigPath: null,
    }),
  ).resolves.toBeUndefined();
});

test("the session hook ingests only its enabled transcript", async () => {
  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-hook-"),
  );
  const paths = createProjectPaths({
    homeDirectory,
    platform: "darwin",
  });
  const transcriptDirectory = path.join(
    paths.claudeProjectsDirectory,
    "fixture",
  );

  await mkdir(transcriptDirectory, { recursive: true });

  const sourcePath = path.join(transcriptDirectory, "session.jsonl");

  await Bun.write(
    sourcePath,
    `${JSON.stringify({
      type: "user",
      sessionId: "session",
      uuid: "event",
      cwd: "/repo",
      message: { id: "message", content: "Use the narrow scope" },
    })}\n`,
  );

  const config = setSourceEnabled({
    config: defaultConfig,
    source: "claude-code",
    enabled: true,
  });

  await writeConfig({ config, configPath: paths.configFile });

  await runSessionEndHook({
    input: JSON.stringify({ transcript_path: sourcePath }),
    configPath: paths.configFile,
    paths,
    managedConfigPath: null,
  });

  const index = await openEventIndex(paths.indexDatabase);

  expect(index.countEvents()).toBe(1);

  index.close();
});

test("the session context keeps learned boundaries advisory", async () => {
  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-boundary-"),
  );
  const paths = createProjectPaths({
    homeDirectory,
    platform: "darwin",
  });

  await writeConfig({ config: defaultConfig, configPath: paths.configFile });

  const origin = await resolveCwdOrigin({
    cwd: homeDirectory,
    enabled: false,
  });

  await writeProfile({
    paths,
    rules: [
      {
        key: "deny-bash",
        title: "Requests confirmation after refusing Bash",
        body: "Ask before repeating a similar Bash action.",
        section: "boundaries",
        scope: "org",
        originDirectory: origin.directoryName,
        repositoryName: null,
        source: "declared",
        status: "active",
        proposal: null,
        appliesWhen: [],
        evidence: { for: ["event:denial"], against: [] },
        observations: 2,
        lastSeen: "2026-09-05",
        sessions: 1,
        origins: [origin.id],
        importReference: null,
      },
    ],
  });

  const context = await getSessionStartContext({
    input: JSON.stringify({ cwd: homeDirectory }),
    configPath: paths.configFile,
    paths,
    managedConfigPath: null,
  });

  expect(context?.hookSpecificOutput.additionalContext).toContain(
    "Requests confirmation after refusing Bash",
  );
});

test("the plugin registers no tool-family blocking hook", async () => {
  const root = await checkoutRoot();
  const hookFiles = [
    path.join(root, ".claude-plugin/hooks/hooks.json"),
    path.join(root, "plugins/shadowclone/hooks/hooks.json"),
  ];

  expect(
    await Bun.file(path.join(root, "plugins/shadowclone/plugin.json")).exists(),
  ).toBeTrue();

  for (const hookFile of hookFiles) {
    expect(await Bun.file(hookFile).exists()).toBeFalse();
  }
});

test("the plugin hook stays silent beside a native Claude integration", async () => {
  const fixture = await integrationFixture();
  const options = {
    input: JSON.stringify({ cwd: fixture.cwd }),
    paths: fixture.paths,
    configPath: fixture.configPath,
    managedConfigPath: null,
  };

  expect(await getSessionStartContext(options)).not.toBeNull();

  await installIntegration({
    ...fixture,
    agent: "claude-code",
    scope: "global",
  });

  expect(await getSessionStartContext(options)).toBeNull();
});
