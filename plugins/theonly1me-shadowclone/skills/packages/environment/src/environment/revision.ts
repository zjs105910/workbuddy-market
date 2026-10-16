import path from "node:path";
import { commitLocalChanges, type FileUpdate } from "@shadowclone/changes";
import type { ProjectPaths } from "@shadowclone/core";
import { authorizedEnvironmentTarget } from "./authorization";
import type { EnvironmentState } from "./types";

export async function publishEnvironmentRevision(options: {
  readonly paths: ProjectPaths;
  readonly updates: readonly FileUpdate[];
  readonly state?: EnvironmentState;
}): Promise<string | null> {
  if (options.updates.length === 0) {
    return null;
  }

  let root = path.dirname(
    options.updates[0]?.filePath ?? options.paths.shadowcloneDirectory,
  );

  for (const update of options.updates) {
    if (
      !(await authorizedEnvironmentTarget({
        paths: options.paths,
        filePath: update.filePath,
        state: options.state,
      }))
    ) {
      throw new Error("Environment change is outside authorized destinations");
    }

    while (
      !path
        .resolve(update.filePath)
        .startsWith(root === path.sep ? root : `${root}${path.sep}`)
    ) {
      root = path.dirname(root);
    }
  }

  return commitLocalChanges({
    paths: options.paths,
    root,
    kind: "environment",
    updates: options.updates,
  });
}
