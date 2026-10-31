import { expect, test } from "bun:test";
import path from "node:path";
import { resolveRepository } from "@shadowclone/sessions";
import { installIntegration } from "./install";
import { nativeSessionStart } from "./hooks";
import { integrationFixture } from "@shadowclone/core/testing";
import { integrationHealth } from "./refresh";

test("global pointer stays stable while its hook injects combined guidance", async () => {
  const fixture = await integrationFixture();
  const repository = await resolveRepository({
    cwd: fixture.cwd,
    enabled: false,
  });

  await Bun.write(
    path.join(
      fixture.paths.profileDirectory,
      "org",
      repository.origin.directoryName,
      "engineering.md",
    ),
    "## Local convention\n\nUse the repository's queue.\n",
  );

  const installed = await installIntegration({
    ...fixture,
    agent: "codex",
    scope: "global",
  });
  const text = await Bun.file(
    path.join(fixture.home, ".codex/AGENTS.md"),
  ).text();

  expect(text).toContain("A session hook loads");
  expect(text).not.toContain("Use complete names.");
  expect(text).not.toContain("repository's queue");

  const output = await nativeSessionStart({
    ...fixture,
    id: installed.id,
    input: JSON.stringify({ cwd: fixture.cwd }),
  });

  expect(JSON.stringify(output)).toContain("repository's queue");
  expect(JSON.stringify(output)).toContain("Use complete names.");
  expect((await integrationHealth(fixture))[0]).toContain(
    "hook delivery observed",
  );
});

test("Cursor global hooks inject combined context and repository installation suppresses duplicate global delivery", async () => {
  const fixture = await integrationFixture();
  const global = await installIntegration({
    ...fixture,
    agent: "cursor",
    scope: "global",
  });
  const input = JSON.stringify({ workspace_roots: [fixture.cwd] });

  expect(
    (await nativeSessionStart({ ...fixture, id: global.id, input }))
      .additional_context,
  ).toContain("Use complete names.");

  await installIntegration({
    ...fixture,
    agent: "cursor",
    scope: "repository",
  });

  expect(
    await nativeSessionStart({ ...fixture, id: global.id, input }),
  ).toEqual({});
});

test("Antigravity receives profile context through native hook output", async () => {
  const fixture = await integrationFixture();
  const installed = await installIntegration({
    ...fixture,
    agent: "antigravity",
    scope: "global",
  });

  const hooks = await Bun.file(
    path.join(fixture.home, ".gemini/config/hooks.json"),
  ).text();
  const skill = Bun.file(
    path.join(
      fixture.home,
      ".gemini/config/skills/shadowclone-context/SKILL.md",
    ),
  );

  const output = await nativeSessionStart({
    ...fixture,
    id: installed.id,
    input: JSON.stringify({
      conversationId: "conversation-1",
      workspacePaths: [fixture.cwd],
    }),
  });

  expect(hooks).toContain("PreInvocation");
  expect(hooks).toContain("Stop");
  expect(await skill.exists()).toBeTrue();
  expect(JSON.stringify(output)).toContain("ephemeralMessage");
  expect(JSON.stringify(output)).toContain("Use complete names.");
});
