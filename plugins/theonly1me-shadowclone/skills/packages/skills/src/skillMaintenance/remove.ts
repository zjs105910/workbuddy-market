import { commitLocalChanges } from "@shadowclone/changes";
import { fingerprint, readLocalText } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";
import { restoreOriginalSkill } from "./render";
import {
  readMaintenanceState,
  skillTarget,
  writeMaintenanceState,
} from "./state";

export async function skillRevisionRoots(
  paths: ProjectPaths,
): Promise<readonly string[]> {
  const state = await readMaintenanceState(paths);

  return [
    ...new Set(
      state.roots.flatMap((root) =>
        root.owner === "third-party" ? [root.destination] : [root.directory],
      ),
    ),
  ];
}

export async function removeSkillMaintenance(
  paths: ProjectPaths,
): Promise<number> {
  const state = await readMaintenanceState(paths);
  const groups = new Map<
    string,
    { filePath: string; previous: string; next: string | null }[]
  >();

  for (const tracked of state.tracked) {
    const root = state.roots.find((entry) => entry.id === tracked.rootId);

    if (!root) {
      throw new Error(
        "Tracked skill root is missing; maintenance state was preserved",
      );
    }

    const directory =
      tracked.kind === "companion" ? root.destination : root.directory;
    const filePath = skillTarget({
      directory,
      relativePath: tracked.relativePath,
    });
    const current = await readLocalText(filePath);

    if (current === null) {
      continue;
    }

    if (fingerprint(current) !== tracked.fingerprint) {
      throw new Error(
        "A maintained skill was edited; reconcile it before forgetting",
      );
    }

    const changes = groups.get(directory) ?? [];

    changes.push({
      filePath,
      previous: current,
      next: tracked.kind === "companion" ? null : restoreOriginalSkill(current),
    });
    groups.set(directory, changes);
  }

  for (const [root, updates] of groups) {
    await commitLocalChanges({ paths, root, kind: "skill", updates });
  }

  await writeMaintenanceState({ paths, state: { ...state, tracked: [] } });

  return state.tracked.length;
}
