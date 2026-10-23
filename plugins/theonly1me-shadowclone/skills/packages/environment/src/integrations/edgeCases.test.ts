import { expect, test } from "bun:test";
import path from "node:path";
import { createProjectPaths } from "@shadowclone/core";
import { installIntegration } from "./install";
import { integrationFixture } from "@shadowclone/core/testing";
import { nativeSessionStart } from "./hooks";
import { refreshIntegrations } from "./refresh";

test("uses the selected Codex home and existing override without losing personal skill discovery", async () => {
  const fixture = await integrationFixture();
  const codexHomeDirectory = path.join(fixture.home, "custom-codex");
  const paths = createProjectPaths({
    homeDirectory: fixture.home,
    platform: "darwin",
    codexHomeDirectory,
  });

  await Bun.write(
    path.join(codexHomeDirectory, "AGENTS.override.md"),
    "User override\n",
  );
  await installIntegration({
    ...fixture,
    paths,
    agent: "codex",
    scope: "global",
  });

  expect(
    await Bun.file(path.join(codexHomeDirectory, "AGENTS.override.md")).text(),
  ).toContain("A session hook loads");
  expect(
    await Bun.file(path.join(codexHomeDirectory, "AGENTS.md")).exists(),
  ).toBeFalse();
  expect(
    await Bun.file(
      path.join(fixture.home, ".agents/skills/shadowclone-context/SKILL.md"),
    ).exists(),
  ).toBeTrue();
});

test("refresh preserves a hook command the user edited", async () => {
  const fixture = await integrationFixture();

  await installIntegration({
    ...fixture,
    agent: "cursor",
    scope: "repository",
  });

  const file = Bun.file(path.join(fixture.cwd, ".cursor/hooks.json"));
  const edited = (await file.text()).replace(
    "shadowclone hook native-start",
    "my-wrapper shadowclone hook native-start",
  );

  await Bun.write(file, edited);

  expect(await refreshIntegrations(fixture)).toEqual({
    refreshed: 0,
    preserved: 1,
  });
  expect(await file.text()).toBe(edited);
});

test("repository hook injects guidance if its native instruction file disappeared", async () => {
  const fixture = await integrationFixture();
  const installed = await installIntegration({
    ...fixture,
    agent: "codex",
    scope: "repository",
  });

  await Bun.file(path.join(fixture.cwd, "AGENTS.override.md")).delete();

  const output = await nativeSessionStart({
    ...fixture,
    id: installed.id,
    input: JSON.stringify({ cwd: fixture.cwd }),
  });

  expect(JSON.stringify(output)).toContain("Use complete names.");
});

test("malformed native input produces a fixed error without echoing its contents", async () => {
  const fixture = await integrationFixture();
  const installed = await installIntegration({
    ...fixture,
    agent: "codex",
    scope: "repository",
  });

  await expect(
    nativeSessionStart({
      ...fixture,
      id: installed.id,
      input: "private native payload",
    }),
  ).rejects.toThrow("Invalid native hook input");
});
