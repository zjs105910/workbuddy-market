import type { FileUpdate } from "@shadowclone/changes";
import type { BuildDefinition, EnvironmentState } from "@shadowclone/environment";
import type { ProjectPaths } from "@shadowclone/core";
import { packagedBuildItems } from "./catalog";
import { planBuildRouting } from "./native";
import { publishBuildSkill } from "./publication";
import { sharedRequirements } from "./requirements";
import { buildLabel } from "./retired";
import type { BuildItem } from "./types";

export type AlwaysOnChange =
  | {
      readonly kind: "added";
      readonly build: BuildDefinition;
      readonly skills: readonly string[];
    }
  | {
      readonly kind: "failed";
      readonly build: BuildDefinition;
      readonly skills: readonly string[];
      readonly reason: string;
    };

type AlwaysOnMigration = {
  readonly state: EnvironmentState;
  readonly updates: readonly FileUpdate[];
  readonly warnings: readonly string[];
  readonly changes: readonly AlwaysOnChange[];
};

function isPublished(options: {
  readonly state: EnvironmentState;
  readonly build: BuildDefinition;
  readonly item: BuildItem;
}): boolean {
  return options.state.artifacts.some(
    (artifact) =>
      artifact.kind === "skill" &&
      artifact.buildId === options.build.id &&
      artifact.buildEntryId === options.item.id,
  );
}

function pendingItems(options: {
  readonly state: EnvironmentState;
  readonly build: BuildDefinition;
  readonly items: readonly BuildItem[];
}): readonly BuildItem[] {
  const coveredByShared =
    options.build.scope === "private"
      ? sharedRequirements({
          state: options.state,
          directory: options.build.directory,
          catalog: options.items,
        })
      : {};

  return options.items.filter(
    (item) =>
      coveredByShared[item.id] !== true &&
      (options.build.choices[item.id] !== true ||
        !isPublished({ state: options.state, build: options.build, item })),
  );
}

async function addToBuild(options: {
  readonly paths: ProjectPaths;
  readonly state: EnvironmentState;
  readonly build: BuildDefinition;
  readonly items: readonly BuildItem[];
}): Promise<Omit<AlwaysOnMigration, "changes">> {
  const build = {
    ...options.build,
    choices: {
      ...options.build.choices,
      ...Object.fromEntries(options.items.map((item) => [item.id, true])),
    },
  };
  const context = { paths: options.paths, cwd: build.directory };
  const updates: FileUpdate[] = [];
  const warnings: string[] = [];
  let state = {
    ...options.state,
    builds: options.state.builds.map((entry) => (entry.id === build.id ? build : entry)),
  };

  for (const item of options.items) {
    if (isPublished({ state, build, item })) {
      continue;
    }

    const added = await publishBuildSkill({
      ...context,
      state,
      build,
      item,
      text: item.text,
      edited: false,
    });

    state = added.state;
    updates.push(...added.updates);
    warnings.push(...added.warnings);
  }

  if (build.scope === "shared") {
    const routing = await planBuildRouting({ ...context, state, build });

    state = routing.state;
    updates.push(...routing.updates);
  }

  return { state, updates, warnings };
}

export async function migrateAlwaysOnSkills(options: {
  readonly paths: ProjectPaths;
  readonly state: EnvironmentState;
}): Promise<AlwaysOnMigration> {
  const alwaysOn = (await packagedBuildItems()).filter(
    (item) => item.kind === "skill" && item.alwaysOn,
  );
  const sharedFirst = options.state.builds
    .toSorted((left, right) => Number(right.scope === "shared") - Number(left.scope === "shared"))
    .map((build) => build.id);
  const updates: FileUpdate[] = [];
  const warnings: string[] = [];
  const changes: AlwaysOnChange[] = [];
  let state = options.state;

  for (const id of sharedFirst) {
    const build = state.builds.find((entry) => entry.id === id);

    if (!build) {
      continue;
    }

    const items = pendingItems({ state, build, items: alwaysOn });
    const skills = items.map((item) => item.name);

    if (items.length === 0) {
      continue;
    }

    try {
      const added = await addToBuild({ paths: options.paths, state, build, items });

      state = added.state;
      updates.push(...added.updates);
      warnings.push(...added.warnings);
      changes.push({ kind: "added", build, skills });
    } catch (error) {
      changes.push({
        kind: "failed",
        build,
        skills,
        reason: error instanceof Error ? error.message : String(error),
      });
    }
  }

  return { state, updates, warnings, changes };
}

export function renderAlwaysOnChanges(changes: readonly AlwaysOnChange[]): readonly string[] {
  return changes.map((change) =>
    change.kind === "added"
      ? `Added ${change.skills.join(", ")} to ${buildLabel(change.build)}. It is always on.`
      : `Could not add ${change.skills.join(", ")} to ${buildLabel(change.build)}: ${change.reason}`,
  );
}
