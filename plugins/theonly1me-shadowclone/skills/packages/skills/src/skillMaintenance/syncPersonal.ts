import path from "node:path";
import type { ProjectPaths } from "@shadowclone/core";
import { discoverSkills } from "./discover";
import { readPortableSkills } from "./portableFiles";
import { registerPortableSkill, syncPortableSkills } from "./portable";
import { readMaintenanceState } from "./state";

export async function syncPersonalSkills(options: {
  readonly paths: ProjectPaths;
}): Promise<{ readonly synced: number; readonly conflicts: number }> {
  const state = await readMaintenanceState(options.paths);
  const personalRoots = state.roots.filter(
    (root) => root.enabled && root.scope === "global" && root.owner === "user",
  );
  const discovered = await discoverSkills(personalRoots);
  const registered = new Set(
    (await readPortableSkills(options.paths)).map((skill) => skill.name),
  );
  let conflicts = 0;
  let synced = 0;

  const candidatesByName = Map.groupBy(
    discovered.skills.filter(
      (skill) => path.dirname(skill.relativePath) === skill.name,
    ),
    (skill) => skill.name,
  );

  for (const [name, candidates] of candidatesByName) {
    if (registered.has(name)) {
      continue;
    }

    if (
      new Set(candidates.map((candidate) => candidate.fingerprint)).size > 1
    ) {
      conflicts += 1;

      continue;
    }

    const [source] = candidates;

    if (!source) {
      continue;
    }

    try {
      await registerPortableSkill({
        paths: options.paths,
        name,
        sourceDirectory: path.dirname(
          path.join(source.root.directory, source.relativePath),
        ),
        managedBy: "adopted",
      });
      registered.add(name);
      synced += 1;
    } catch (error) {
      if (
        !(error instanceof Error) ||
        error.message !==
          "A different skill already exists at a portable destination"
      ) {
        throw error;
      }

      conflicts += 1;
    }
  }

  const maintained = await syncPortableSkills({ paths: options.paths });

  return {
    synced: synced + maintained.synced,
    conflicts: conflicts + maintained.conflicts,
  };
}
