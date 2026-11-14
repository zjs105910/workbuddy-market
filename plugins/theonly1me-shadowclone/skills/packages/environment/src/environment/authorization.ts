import path from "node:path";
import type { ProjectPaths } from "@shadowclone/core";
import { canonicalPath } from "@shadowclone/core";
import { readIntegrations } from "../integrations/state";
import {
  integrationFilePath,
  integrationTargets,
} from "../integrations/targets";
import { readMaintenanceState } from "@shadowclone/skills";
import { readEnvironment, environmentFile } from "./store";
import { learningScopes, skillDirectories } from "./scope";
import type { EnvironmentState } from "./types";
import { buildIntegrations } from "./builds/integrations";
import { buildDirectories } from "./builds/directories";

export async function authorizedEnvironmentTarget(options: {
  readonly paths: ProjectPaths;
  readonly filePath: string;
  readonly state?: EnvironmentState;
}): Promise<boolean> {
  const target = path.resolve(options.filePath);

  if (target === environmentFile(options.paths)) {
    return true;
  }
  if (target === path.join(options.paths.shadowcloneDirectory, "learning-pending.json")) return true;

  if (
    target ===
    path.join(options.paths.shadowcloneDirectory, "integrations.json")
  ) {
    return true;
  }

  const state = options.state ?? (await readEnvironment(options.paths));

  if (state === null) {
    return false;
  }

  const roots = learningScopes({ paths: options.paths, state }).flatMap(
    skillDirectories,
  );

  roots.push(
    ...state.builds.flatMap((build) =>
      buildDirectories({ paths: options.paths, cwd: build.directory, build }),
    ),
  );

  const maintenance = await readMaintenanceState(options.paths);

  roots.push(
    ...maintenance.roots
      .filter((root) => root.enabled && root.owner === "user")
      .map((root) => root.directory),
  );

  if (
    roots.some((root) => {
      const relative = path
        .relative(canonicalPath(root), target)
        .split(path.sep)
        .join("/");

      return (
        /^[a-z0-9]+(?:-[a-z0-9]+)*\/.+/.test(relative) &&
        !relative
          .split("/")
          .some((segment) => segment === ".." || segment === ".git")
      );
    })
  ) {
    return true;
  }

  if (
    state.repositories.some(({ directory }) =>
      ["AGENTS.md", "CLAUDE.md"].some(
        (name) => path.join(directory, name) === target,
      ),
    )
  ) {
    return true;
  }

  if (
    state.builds.some(
      (build) =>
        build.scope === "shared" &&
        ["AGENTS.md", "CLAUDE.md"].some(
          (name) => path.join(build.directory, name) === target,
        ),
    )
  ) {
    return true;
  }

  if (
    state.builds.length > 0 &&
    (
      await buildIntegrations({
        paths: options.paths,
        cwd: path.dirname(options.paths.shadowcloneDirectory),
      })
    ).some((integration) =>
      integrationTargets(integration).some(
        (file) => integrationFilePath({ integration, file }) === target,
      ),
    )
  ) {
    return true;
  }

  return (await readIntegrations(options.paths)).some((integration) =>
    integration.files.some(
      (file) => integrationFilePath({ integration, file }) === target,
    ),
  );
}
