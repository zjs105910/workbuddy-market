import { expect, test } from "bun:test";
import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { readConfig, createProjectPaths } from "@shadowclone/core";
import { readEnvironment } from "@shadowclone/environment";
import { initialize } from "./init";

test("explicit consent skips interactive questions", async () => {
  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-init-consent-"),
  );
  const paths = createProjectPaths({ homeDirectory, platform: "darwin" });

  await initialize({
    paths,
    workingDirectory: homeDirectory,
    presence: {
      hasRepositoryGuidance: false,
      presentCaptureSources: new Set(),
    },
    agents: [],
    consent: { learn: false, skills: true, background: false },
    ask: () => {
      throw new Error("Explicit consent must not prompt");
    },
    writeLine: () => {},
  });

  const config = await readConfig({ configPath: paths.configFile });
  expect(config.sources["skill-library"]).toBeTrue();
  expect(config.distillation.automatic).toBeFalse();
});

test("skill-only setup does not register repository metadata", async () => {
  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-init-skill-only-"),
  );
  const paths = createProjectPaths({ homeDirectory, platform: "darwin" });

  await initialize({
    paths,
    workingDirectory: homeDirectory,
    presence: {
      hasRepositoryGuidance: true,
      presentCaptureSources: new Set(),
    },
    agents: [],
    consent: { learn: false, skills: true, background: false },
    readRemote: async () => "https://github.com/example/synthetic.git",
    writeLine: () => {},
  });

  expect((await readEnvironment(paths))?.repositories).toEqual([]);
});
