import { expect, test } from "bun:test";
import path from "node:path";
import { chmod, lstat } from "node:fs/promises";
import { skillFixture } from "./testing";
import { discoverSkills, readMaintenanceState } from "@shadowclone/skills";
import { emptyEnvironment } from "./types";
import { environmentFile, writeEnvironment, renderEnvironment } from "./store";
import { readLocalText } from "@shadowclone/core";
import { skillPublication } from "./publication";
import { publishEnvironmentRevision } from "./revision";
import { materializeSkillDelivery } from "./delivery";
import { undoRevision } from "./undo";

test("portable publication and dispatch retain resource bytes and executable modes, with grouped undo", async () => {
  const setup = await skillFixture();
  const script = path.join(setup.directory, "scripts/check.sh");
  const asset = path.join(setup.directory, "assets/sample.bin");

  await Bun.write(script, "#!/bin/sh\nexit 0\n");
  await chmod(script, 0o700);

  const bytes = new Uint8Array([0, 255, 128, 35]);

  await Bun.write(asset, bytes);

  const { skills } = await discoverSkills(
    (await readMaintenanceState(setup.paths)).roots,
  );
  const skill = skills.find((entry) => entry.name === "typed-changes");

  if (!skill) {
    throw new Error("Expected fixture skill");
  }

  const state = { ...emptyEnvironment, phase: "active" as const };

  await writeEnvironment({ paths: setup.paths, state });

  const publication = await skillPublication({
    paths: setup.paths,
    state,
    scope: { key: "global", directory: setup.home, repository: null },
    skill,
    name: skill.name,
    text: `${skill.raw}\nRun [check](scripts/check.sh).\n`,
    records: [],
  });

  const filePath = environmentFile(setup.paths);

  const revision = await publishEnvironmentRevision({
    paths: setup.paths,
    updates: [
      ...publication.updates,
      {
        filePath,
        previous: await readLocalText(filePath),
        next: renderEnvironment(publication.state),
      },
    ],
  });

  const canonical = path.join(setup.home, ".agents/skills/typed-changes");

  expect(
    new Uint8Array(
      await Bun.file(path.join(canonical, "assets/sample.bin")).arrayBuffer(),
    ),
  ).toEqual(bytes);
  expect(
    (await lstat(path.join(canonical, "scripts/check.sh"))).mode & 0o777,
  ).toBe(0o700);

  const destination = path.join(setup.home, "dispatch");
  const routing = await materializeSkillDelivery({
    paths: setup.paths,
    repositoryDirectory: setup.cwd,
    destination,
  });

  expect(routing).toContain(
    path.join(destination, ".shadowclone-skills/0/typed-changes/SKILL.md"),
  );
  expect(
    new Uint8Array(
      await Bun.file(
        path.join(
          destination,
          ".shadowclone-skills/0/typed-changes/assets/sample.bin",
        ),
      ).arrayBuffer(),
    ),
  ).toEqual(bytes);

  if (!revision) {
    throw new Error("Expected publication revision");
  }

  await undoRevision({ paths: setup.paths, id: revision });

  expect(
    await Bun.file(path.join(canonical, "assets/sample.bin")).exists(),
  ).toBeFalse();
  expect(await Bun.file(setup.filePath).text()).toBe(setup.original);
  expect(new Uint8Array(await Bun.file(asset).arrayBuffer())).toEqual(bytes);
});
