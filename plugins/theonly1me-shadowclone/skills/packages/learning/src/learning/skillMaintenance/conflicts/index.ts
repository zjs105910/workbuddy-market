import path from "node:path";
import type { LearningExecution } from "@shadowclone/agents";
import { acquireLocalLock } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";
import { discoverDeliverySkills, readMaintenanceState } from "@shadowclone/skills";
import { reviewDiscoveredSkills } from "./review";

export async function reviewSkillConflicts(options: {
  readonly paths: ProjectPaths;
  readonly execution: LearningExecution;
  readonly repositoryDirectories: readonly string[];
}) {
  const lock = await acquireLocalLock(path.join(options.paths.shadowcloneDirectory, "skills-worker.db"));
  if (!lock) throw new Error("Another skill library review is running");

  try {
    const state = await readMaintenanceState(options.paths);
    const discovered = await discoverDeliverySkills(state.roots.filter((root) =>
      root.enabled && (root.scope === "global" || options.repositoryDirectories.includes(root.cwd)),
    ));
    const result = await reviewDiscoveredSkills({
      ...options,
      state,
      skills: discovered.skills.filter((skill) => skill.valid !== false),
    });

    return { ...result, deferred: result.deferred + discovered.invalid };
  } finally {
    lock.release();
  }
}
