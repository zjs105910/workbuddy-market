import path from "node:path";
import type { BuildDefinition, EnvironmentState } from "@shadowclone/environment";
import type { BuildItem } from "./types";

export function sharedRequirements(options: {
  readonly state: EnvironmentState;
  readonly directory: string;
  readonly catalog: readonly BuildItem[];
}): Readonly<Record<string, boolean>> {
  const locked: Record<string, boolean> = {};

  const shared = options.state.builds.filter(
    (build) =>
      build.scope === "shared" &&
      (build.directory === options.directory ||
        options.directory.startsWith(`${build.directory}${path.sep}`)),
  );

  for (const build of shared) {
    for (const item of options.catalog) {
      if (!build.choices[item.id]) {
        continue;
      }

      locked[item.id] = true;

      for (const sibling of options.catalog) {
        if (item.axis && sibling.axis === item.axis && sibling.id !== item.id) {
          locked[sibling.id] = false;
        }
      }
    }
  }

  return locked;
}

export function validateSharedRequirements(options: {
  readonly state: EnvironmentState;
  readonly build: BuildDefinition;
  readonly catalog: readonly BuildItem[];
}): Readonly<Record<string, boolean>> {
  if (options.build.scope !== "private") {
    return {};
  }

  const locked = sharedRequirements({
    ...options,
    directory: options.build.directory,
  });

  const alwaysOnIds = new Set(
    options.catalog.filter((item) => item.alwaysOn).map((item) => item.id),
  );

  for (const [id, enabled] of Object.entries(locked)) {
    const choice = options.build.choices[id];

    if (
      (choice !== undefined && choice !== enabled && !alwaysOnIds.has(id)) ||
      options.build.edits[id]
    ) {
      throw new Error(
        "Personal choices cannot change shared requirements; edit the shared build for review",
      );
    }
  }

  return locked;
}
