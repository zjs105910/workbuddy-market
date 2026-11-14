import { expect, test } from "bun:test";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { skillFixture } from "./testing";
import { registerWorkingRepository } from "./registerRepository";
import { readEnvironment, writeEnvironment } from "./store";
import { emptyEnvironment } from "./types";

test("setup registers a verified working repository once so scoped learning can publish", async () => {
  const setup = await skillFixture();
  const workspace = path.join(setup.home, "tally");
  await mkdir(workspace);
  await writeEnvironment({ paths: setup.paths, state: { ...emptyEnvironment, phase: "active", automatic: true } });
  const options = {
    paths: setup.paths, workingDirectory: workspace, blockedOrigins: [], managedConfigPath: null,
    readRemote: async () => "git@github.com:synthetic-org/tally.git",
  };

  expect(await registerWorkingRepository({ ...options, gitMetadataEnabled: false })).toBeNull();
  expect((await readEnvironment(setup.paths))?.repositories).toEqual([]);

  const registered = await registerWorkingRepository({ ...options, gitMetadataEnabled: true });
  expect(registered?.repositoryName).toStartWith("tally");
  expect((await readEnvironment(setup.paths))?.repositories).toEqual([expect.objectContaining({ repositoryName: registered?.repositoryName })]);
  expect(await registerWorkingRepository({ ...options, gitMetadataEnabled: true })).toBeNull();
});

test("unknown and blocked origins stay unregistered", async () => {
  const setup = await skillFixture();
  const workspace = path.join(setup.home, "scratch");
  await mkdir(workspace);
  await writeEnvironment({ paths: setup.paths, state: { ...emptyEnvironment, phase: "active", automatic: true } });
  const base = { paths: setup.paths, workingDirectory: workspace, gitMetadataEnabled: true, managedConfigPath: null };

  expect(await registerWorkingRepository({ ...base, blockedOrigins: [], readRemote: async () => null })).toBeNull();
  expect(await registerWorkingRepository({
    ...base, blockedOrigins: ["github.com/synthetic-org/*"], readRemote: async () => "git@github.com:synthetic-org/tally.git",
  })).toBeNull();
  expect((await readEnvironment(setup.paths))?.repositories).toEqual([]);
});
