import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import {
  defaultConfig,
  writeConfig,
  type ShadowcloneConfig,
  canonicalPath,
  createProjectPaths,
  type ProjectPaths,
} from "@shadowclone/core";
import {
  materializeFixture,
  type FixtureRepository,
} from "./fixtures/materialize";

export type HarnessTestSetup = {
  readonly home: string;
  readonly paths: ProjectPaths;
  readonly root: string;
};

export async function harnessTestSetup(options: {
  readonly fixture: FixtureRepository;
  readonly globalRules?: string;
  readonly sources?: Partial<ShadowcloneConfig["sources"]>;
}): Promise<HarnessTestSetup> {
  const home = canonicalPath(
    await mkdtemp(path.join(os.tmpdir(), "shadowclone-harness-")),
  );
  const paths = createProjectPaths({ homeDirectory: home, platform: "linux" });

  await writeConfig({
    configPath: paths.configFile,
    config: {
      ...defaultConfig,
      sources: {
        ...defaultConfig.sources,
        "repository-manifests": true,
        ...options.sources,
      },
    },
  });

  if (options.globalRules !== undefined) {
    await Bun.write(
      path.join(paths.profileDirectory, "global/engineering.md"),
      options.globalRules,
    );
  }

  const root = await materializeFixture({
    fixture: options.fixture,
    parent: path.join(home, "work"),
  });

  return { home, paths, root };
}

export function acceptAll(): boolean {
  return true;
}
