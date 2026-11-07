import { expect, test } from "bun:test";
import path from "node:path";
import { integrationFixture } from "@shadowclone/core/testing";
import {
  artifactRelativePaths,
  compileContext,
  readInstallations,
  writeInstallations,
} from "@shadowclone/environment";
import { renderAgent } from "@shadowclone/profile";
import { removeUneditedLegacySubagent } from "./legacyUpgrade";

async function legacyFixture() {
  const fixture = await integrationFixture();
  const profile = await compileContext({
    ...fixture,
    paths: fixture.paths,
    cwd: fixture.cwd,
  });

  if (profile === null) {
    throw new Error("Fixture profile is unavailable");
  }

  const filePath = path.join(fixture.cwd, artifactRelativePaths.agent);

  await Bun.write(filePath, renderAgent({ profile }));
  await writeInstallations({
    filePath: fixture.paths.installationsFile,
    state: {
      version: 1,
      installations: [
        {
          directory: fixture.cwd,
          artifacts: ["agent"],
          excludes: [".claude/agents/shadowclone.md"],
        },
      ],
    },
  });

  return { ...fixture, filePath };
}

test("removes only an unchanged recorded legacy subagent", async () => {
  const fixture = await legacyFixture();

  expect(
    await removeUneditedLegacySubagent({
      cwd: fixture.cwd,
      paths: fixture.paths,
    }),
  ).toBeTrue();
  expect(await Bun.file(fixture.filePath).exists()).toBeFalse();
  expect(
    (await readInstallations(fixture.paths.installationsFile)).installations,
  ).toEqual([]);
});

test("preserves an edited legacy subagent", async () => {
  const fixture = await legacyFixture();

  await Bun.write(fixture.filePath, "User-edited subagent\n");

  expect(
    await removeUneditedLegacySubagent({
      cwd: fixture.cwd,
      paths: fixture.paths,
    }),
  ).toBeFalse();
  expect(await Bun.file(fixture.filePath).text()).toBe(
    "User-edited subagent\n",
  );
});
