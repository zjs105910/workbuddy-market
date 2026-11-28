import { expect, test } from "bun:test";
import { rm } from "node:fs/promises";
import path from "node:path";
import { writeConfig, defaultConfig } from "@shadowclone/core";
import { installIntegration } from "./install";
import { nativeSessionStart } from "./hooks";
import { integrationFixture } from "@shadowclone/core/testing";

test("redacts a profile secret before native hook delivery", async () => {
  const fixture = await integrationFixture();
  const secret = ["sk", "live", "0123456789abcdefghij"].join("_");

  await Bun.write(
    path.join(fixture.paths.profileDirectory, "global/engineering.md"),
    `## Credentials\n\nNever use ${secret}.\n`,
  );

  const installed = await installIntegration({
    ...fixture,
    agent: "claude-code",
    scope: "repository",
  });
  const pointer = await Bun.file(
    path.join(fixture.cwd, "CLAUDE.local.md"),
  ).text();
  const output = JSON.stringify(
    await nativeSessionStart({
      ...fixture,
      id: installed.id,
      input: JSON.stringify({ cwd: fixture.cwd }),
    }),
  );

  expect(pointer).not.toContain(secret);
  expect(output).not.toContain(secret);
  expect(output).toContain("[redacted:");
});

test("Claude session hooks deliver the preference index without learning instructions", async () => {
  const fixture = await integrationFixture();

  await writeConfig({
    configPath: fixture.paths.configFile,
    config: { ...defaultConfig, distillation: { deep: true, automatic: true } },
  });

  const installed = await installIntegration({
    ...fixture,
    agent: "claude-code",
    scope: "repository",
  });

  for (const hookEventName of ["SubagentStart", "SessionStart"]) {
    const output = await nativeSessionStart({
      ...fixture,
      id: installed.id,
      input: JSON.stringify({
        cwd: fixture.cwd,
        session_id: "claude-session",
        hook_event_name: hookEventName,
      }),
    });
    const text = JSON.stringify(output);

    expect(output).toMatchObject({ hookSpecificOutput: { hookEventName } });
    expect(text).toContain("- Naming: Use complete names.");
    expect(text).not.toContain("learn --session");
  }

  expect(
    await Bun.file(
      path.join(fixture.paths.shadowcloneDirectory, "session-learning.json"),
    ).exists(),
  ).toBeFalse();
});

test("an empty profile produces no native hook output", async () => {
  const fixture = await integrationFixture();

  await rm(path.join(fixture.paths.profileDirectory, "global/engineering.md"));

  const installed = await installIntegration({
    ...fixture,
    agent: "claude-code",
    scope: "repository",
  });
  const output = await nativeSessionStart({
    ...fixture,
    id: installed.id,
    input: JSON.stringify({
      cwd: fixture.cwd,
      session_id: "claude-session",
      hook_event_name: "SessionStart",
    }),
  });

  expect(output).toEqual({});
});

test("installation leaves capture consent unchanged", async () => {
  const fixture = await integrationFixture();

  await writeConfig({
    config: defaultConfig,
    configPath: fixture.paths.configFile,
  });

  const previous = await Bun.file(fixture.paths.configFile).text();

  await installIntegration({
    ...fixture,
    agent: "claude-code",
    scope: "repository",
  });

  expect(await Bun.file(fixture.paths.configFile).text()).toBe(previous);
});
