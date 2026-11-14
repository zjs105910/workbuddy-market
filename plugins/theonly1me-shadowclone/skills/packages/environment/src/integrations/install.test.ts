import { expect, test } from "bun:test";
import path from "node:path";
import { installIntegration, uninstallIntegration } from "./install";
import { integrationFixture } from "@shadowclone/core/testing";
import { readIntegrations } from "./state";
import { refreshIntegrations } from "./refresh";

test("preserves surrounding Codex instructions across refresh, repeat install and uninstall", async () => {
  const fixture = await integrationFixture();
  const destination = path.join(fixture.cwd, "AGENTS.md");
  const localDestination = path.join(fixture.cwd, "AGENTS.override.md");
  const original = "# Team guidance\n\nUse the existing service.";
  const userOverride = "# My overrides\n\nPrefer small commits.\n";

  await Bun.write(destination, original);
  await Bun.write(localDestination, userOverride);

  const first = await installIntegration({
    ...fixture,
    agent: "codex",
    scope: "repository",
  });

  expect(await Bun.file(destination).text()).toBe(original);
  expect(await Bun.file(localDestination).text()).toStartWith(userOverride);
  expect(await Bun.file(localDestination).text()).toContain("A session hook loads");
  expect(
    await Bun.file(path.join(fixture.cwd, ".codex/hooks.json")).json(),
  ).not.toHaveProperty("hooks.SubagentStart");

  const second = await installIntegration({
    ...fixture,
    agent: "codex",
    scope: "repository",
  });

  expect(first.id).toBe(second.id);

  await Bun.write(
    path.join(fixture.paths.profileDirectory, "global/engineering.md"),
    "## Naming\n\nPrefer named exports.\n",
  );

  expect(await refreshIntegrations(fixture)).toEqual({
    refreshed: 1,
    preserved: 0,
  });

  const text = await Bun.file(localDestination).text();

  expect(text).toContain("A session hook loads");
  expect(text).toContain("run `shadowclone context`");
  expect(text).not.toContain("Prefer named exports.");
  expect(text).not.toContain("Use complete names.");

  const [installed] = await readIntegrations(fixture.paths);

  if (!installed) {
    throw new Error("Missing installation");
  }

  await uninstallIntegration({ paths: fixture.paths, integration: installed });

  expect(await Bun.file(destination).text()).toBe(original);
  expect(await Bun.file(localDestination).text()).toBe(userOverride);
  expect(await readIntegrations(fixture.paths)).toEqual([]);
});

test("preserves manual edits to managed content and refuses destructive uninstall", async () => {
  const fixture = await integrationFixture();
  const installed = await installIntegration({
    ...fixture,
    agent: "claude-code",
    scope: "repository",
  });
  const destination = path.join(fixture.cwd, "CLAUDE.local.md");
  const edited = (await Bun.file(destination).text()).replace(
    "A session hook loads",
    "my own session wrapper",
  );

  await Bun.write(destination, edited);

  expect(await refreshIntegrations(fixture)).toEqual({
    refreshed: 0,
    preserved: 1,
  });
  await expect(
    uninstallIntegration({ paths: fixture.paths, integration: installed }),
  ).rejects.toThrow("edited");
  expect(await Bun.file(destination).text()).toBe(edited);
});

test("preserves unrelated hooks and settings", async () => {
  const fixture = await integrationFixture();
  const destination = path.join(fixture.cwd, ".claude/settings.local.json");
  const original = {
    permissions: { deny: ["Bash(curl *)"] },
    hooks: {
      SessionStart: [{ hooks: [{ type: "command", command: "team-check" }] }],
    },
  };

  await Bun.write(destination, JSON.stringify(original));

  const installed = await installIntegration({
    ...fixture,
    agent: "claude-code",
    scope: "repository",
  });
  const installedHooks = (await Bun.file(destination).json()).hooks;

  expect(installedHooks.SessionStart).toHaveLength(2);
  expect(installedHooks.SubagentStart).toBeUndefined();
  expect(installedHooks.SessionStart[1].hooks[0].command).toContain('$HOME/.shadowclone/bin/shadowclone');
  expect(await Bun.file(path.join(fixture.paths.shadowcloneDirectory, "bin/shadowclone")).exists()).toBeTrue();

  await uninstallIntegration({ paths: fixture.paths, integration: installed });

  expect(await Bun.file(destination).json()).toEqual(original);
});

test("creates a Cursor always-applied rule and a valid integration skill", async () => {
  const fixture = await integrationFixture();

  await installIntegration({
    ...fixture,
    agent: "cursor",
    scope: "repository",
  });

  expect(
    await Bun.file(
      path.join(fixture.cwd, ".cursor/rules/shadowclone.mdc"),
    ).text(),
  ).toStartWith("---\ndescription:");
  expect(
    await Bun.file(
      path.join(fixture.cwd, ".cursor/skills/shadowclone-context/SKILL.md"),
    ).text(),
  ).toStartWith("---\nname: shadowclone-context");
});
