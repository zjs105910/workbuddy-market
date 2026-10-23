import { expect, test } from "bun:test";
import path from "node:path";
import { defaultConfig, writeConfig } from "@shadowclone/core";
import { openEventIndex } from "@shadowclone/sessions";
import { integrationFixture } from "@shadowclone/core/testing";
import { learn } from "./learn";

test("learning keeps an observed session bound to its original repository", async () => {
  const setup = await integrationFixture();

  await writeConfig({
    configPath: setup.paths.configFile,
    config: {
      ...defaultConfig,
      sources: {
        ...defaultConfig.sources,
        "claude-code": true,
        "git-metadata": true,
      },
    },
  });

  const index = await openEventIndex(setup.paths.indexDatabase);
  const timestamp = new Date(Date.now() + 1_000).toISOString();

  index.close();
  await Bun.write(
    path.join(setup.paths.claudeProjectsDirectory, "session.jsonl"),
    `${JSON.stringify({
      type: "user",
      sessionId: "fixture-session",
      uuid: "fixture-event",
      timestamp,
      cwd: setup.cwd,
      message: { content: "Use complete variable names." },
    })}\n`,
  );

  let remoteReads = 0;
  const readRemote = async () => {
    remoteReads += 1;

    return remoteReads === 1
      ? "git@github.com:first-owner/project.git"
      : "git@github.com:second-owner/project.git";
  };

  await learn({ ...setup, readRemote, writeLine: () => undefined });
  await learn({ ...setup, readRemote, writeLine: () => undefined });

  expect(remoteReads).toBe(1);
});
