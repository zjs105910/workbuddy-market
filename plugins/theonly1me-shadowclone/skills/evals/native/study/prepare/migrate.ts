import { cp, mkdir } from "node:fs/promises";
import path from "node:path";
import { createLearningExecution } from "@shadowclone/agents";
import type { EngineRunner } from "@shadowclone/agents";
import { activateEnvironment, prepareEnvironmentMigration } from "@shadowclone/environment";
import { updateLearningEnvironment } from "@shadowclone/learning";
import type { ProjectPaths } from "@shadowclone/core";
import type { GitRemoteReader } from "@shadowclone/sessions";

export async function migrateLegacyProfile(options: {
  readonly paths: ProjectPaths;
  readonly sourceProfileDirectory: string;
  readonly workspace: string;
  readonly runner: EngineRunner;
  readonly readRemote: GitRemoteReader;
  readonly passes: number;
  readonly writeLine: (line: string) => void;
}): Promise<{ readonly records: number; readonly repositories: number; readonly passes: readonly string[]; readonly activation: string }> {
  await mkdir(options.paths.shadowcloneDirectory, { recursive: true, mode: 0o700 });
  await cp(options.sourceProfileDirectory, options.paths.profileDirectory, { recursive: true, dereference: true });
  await cp(path.join(path.dirname(options.sourceProfileDirectory), "config.toml"), options.paths.configFile);
  const state = await prepareEnvironmentMigration({
    paths: options.paths, repositories: [options.workspace], automatic: true, apply: true,
    readRemote: options.readRemote, managedConfigPath: null,
  });
  const execution = createLearningExecution({ engine: "codex", runner: options.runner });
  const passes: string[] = [];

  for (let pass = 0; pass < options.passes; pass += 1) {
    const summary = await updateLearningEnvironment({ paths: options.paths, execution, readRemote: options.readRemote, managedConfigPath: null });
    const line = JSON.stringify(summary);
    passes.push(line);
    options.writeLine(line);
    if (!/"pending":[1-9]/.test(line)) break;
  }

  const activation = await activateEnvironment(options.paths)
    .then((revision) => `activated ${revision ?? "unchanged"}`)
    .catch((error: unknown) => `not activated: ${error instanceof Error ? error.message : "unknown"}`);
  return { records: state.records.length, repositories: state.repositories.length, passes, activation };
}
