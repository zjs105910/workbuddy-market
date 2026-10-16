import type { FileUpdate } from "@shadowclone/changes";
import type { BuildDefinition, EnvironmentState } from "@shadowclone/environment";
import type { ProjectPaths } from "@shadowclone/core";
import { loadSeedLibrary } from "@shadowclone/skills";
import { packagedBuildItems } from "./catalog";
import { planBuildRouting } from "./native";
import { publishBuildSkill } from "./publication";
import {
  activeRetirements,
  retiredBundledSkills,
  type RetiredSkill,
  type RetiredSkillChange,
} from "./retired";
import { retireBuildSkills } from "./retirement";
import { changedOutsideBundle, installedFiles } from "./sync";

type Migration = {
  readonly state: EnvironmentState;
  readonly updates: readonly FileUpdate[];
  readonly warnings: readonly string[];
};

type SelectedRetirement = RetiredSkill & { readonly id: string };

type KeptRetiredSkill = Extract<RetiredSkillChange, { readonly kind: "kept" }>;

async function keptRetiredSkills(options: {
  readonly state: EnvironmentState;
  readonly build: BuildDefinition;
  readonly selected: readonly SelectedRetirement[];
}): Promise<readonly KeptRetiredSkill[]> {
  const kept: KeptRetiredSkill[] = [];

  for (const entry of options.selected) {
    const base = {
      kind: "kept",
      build: options.build,
      retired: entry.id,
      replacement: entry.replacement,
    } as const;

    if (options.build.edits[entry.id] !== undefined) {
      kept.push({ ...base, filePath: null });

      continue;
    }

    const artifacts = options.state.artifacts.filter(
      (artifact) => artifact.buildId === options.build.id && artifact.buildEntryId === entry.id,
    );
    const files = await installedFiles({
      copies: artifacts.filter((artifact) => artifact.kind === "skill"),
      resources: artifacts.filter((artifact) => artifact.kind === "resource"),
    });

    kept.push(
      ...files
        .filter((file) => changedOutsideBundle({ skill: entry.id, file }))
        .map((file) => ({ ...base, filePath: file.artifact.filePath })),
    );
  }

  return kept;
}

async function migrateBuild(options: {
  readonly paths: ProjectPaths;
  readonly state: EnvironmentState;
  readonly build: BuildDefinition;
  readonly retiredIds: readonly string[];
  readonly replacements: readonly string[];
}): Promise<Migration> {
  const choices = Object.fromEntries(
    Object.entries(options.build.choices).filter(([id]) => !options.retiredIds.includes(id)),
  );

  for (const replacement of options.replacements) {
    choices[replacement] = true;
  }

  const build = { ...options.build, choices };
  const context = { paths: options.paths, cwd: build.directory };
  const items = await packagedBuildItems();
  const updates: FileUpdate[] = [];
  const warnings: string[] = [];
  let state = {
    ...options.state,
    builds: options.state.builds.map((entry) => (entry.id === build.id ? build : entry)),
  };

  for (const replacement of options.replacements) {
    const item = items.find((candidate) => candidate.id === replacement);

    if (!item) {
      throw new Error(`The bundled skill ${replacement} is missing from this installation`);
    }

    if (
      state.artifacts.some(
        (artifact) => artifact.buildId === build.id && artifact.buildEntryId === replacement,
      )
    ) {
      continue;
    }

    const published = await publishBuildSkill({
      ...context,
      state,
      build,
      item,
      text: item.text,
      edited: false,
    });

    state = published.state;
    updates.push(...published.updates);
    warnings.push(...published.warnings);
  }

  const retired = await retireBuildSkills({
    state,
    build,
    retained: new Set(
      state.artifacts
        .filter((artifact) => artifact.buildId === build.id)
        .map((artifact) => artifact.buildEntryId ?? "")
        .filter((id) => !options.retiredIds.includes(id)),
    ),
  });
  const routing =
    build.scope === "shared"
      ? await planBuildRouting({ ...context, state: retired.state, build })
      : { state: retired.state, updates: [] };

  return {
    state: routing.state,
    updates: [...updates, ...retired.updates, ...routing.updates],
    warnings: [...warnings, ...retired.warnings],
  };
}

export async function migrateRetiredSkills(options: {
  readonly paths: ProjectPaths;
  readonly state: EnvironmentState;
  readonly retired?: ReadonlyMap<string, RetiredSkill>;
  readonly libraryIds?: ReadonlySet<string>;
}): Promise<Migration & { readonly changes: readonly RetiredSkillChange[] }> {
  const active = activeRetirements({
    retired: options.retired ?? retiredBundledSkills,
    libraryIds:
      options.libraryIds ?? new Set((await loadSeedLibrary()).guidance.map((entry) => entry.id)),
  });
  const updates: FileUpdate[] = [];
  const warnings: string[] = [];
  const changes: RetiredSkillChange[] = [];
  let state = options.state;

  for (const build of options.state.builds) {
    const retiredIds = Object.keys(build.choices)
      .filter((id) => active.has(id))
      .sort();
    const selected = retiredIds.flatMap((id) => {
      const entry = active.get(id);

      return entry && build.choices[id] ? [{ ...entry, id }] : [];
    });

    const kept = await keptRetiredSkills({ state, build, selected });
    const keptIds = new Set(kept.map((change) => change.retired));
    const removedIds = retiredIds.filter((id) => !keptIds.has(id));
    const replacing = selected.filter((entry) => !keptIds.has(entry.id));
    const replacements = [...new Set(replacing.map((entry) => entry.replacement))];

    changes.push(...kept);

    if (removedIds.length === 0) {
      continue;
    }

    try {
      const migrated = await migrateBuild({
        paths: options.paths,
        state,
        build,
        retiredIds: removedIds,
        replacements,
      });

      state = migrated.state;
      updates.push(...migrated.updates);
      warnings.push(...migrated.warnings);
    } catch (error) {
      changes.push({
        kind: "failed",
        build,
        retired: removedIds,
        replacements,
        reason: error instanceof Error ? error.message : String(error),
      });

      continue;
    }

    for (const replacement of replacements) {
      const replaced = replacing.filter((entry) => entry.replacement === replacement);

      changes.push({
        kind: "replaced",
        build,
        retired: replaced.map((entry) => entry.id),
        replacement,
        preferences: replaced.flatMap((entry) =>
          entry.defaultPreference ? [{ retired: entry.id, text: entry.defaultPreference }] : [],
        ),
      });
    }
  }

  return { state, updates, warnings, changes };
}
