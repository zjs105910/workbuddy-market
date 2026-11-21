import { rmdir } from "node:fs/promises";
import path from "node:path";
import { commitLocalChanges } from "@shadowclone/changes";
import { acquireLocalLock } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";
import { createProfileRepairPlan } from "./plan";
import type { ProfileRepairPlan } from "./types";

export { applyProfileCuration } from "./curation";

export { createProfileCurationPlan } from "./curationPlan";

export type { ProfileCurationPlan } from "./curationPlan";

export {
  parseProfileCurationDecisions,
  type ProfileCurationDecision,
  type ProfileCurationDecisions,
} from "./decisions";

async function removeEmptyLegacyDirectories(options: {
  readonly paths: ProjectPaths;
  readonly plan: ProfileRepairPlan;
}): Promise<void> {
  for (const repair of options.plan.repairs) {
    for (const root of ["org", path.join("references", "org")]) {
      const directory = path.join(
        options.paths.profileDirectory,
        root,
        repair.sourceDirectory,
      );
      const descendants = [path.join(directory, "projects"), directory];

      for (const descendant of descendants) {
        await rmdir(descendant).catch(() => undefined);
      }
    }
  }
}

export { createProfileRepairPlan } from "./plan";

export type {
  BlockedOriginRepair,
  OriginRepair,
  ProfileRepairPlan,
} from "./types";

export async function applyProfileRepair(options: {
  readonly paths: ProjectPaths;
  readonly plan?: ProfileRepairPlan;
}): Promise<{
  readonly revisionId: string | null;
  readonly plan: ProfileRepairPlan;
}> {
  const lock = await acquireLocalLock(
    path.join(options.paths.shadowcloneDirectory, "profile-write.db"),
  );

  if (!lock) {
    throw new Error("Another profile update is running; retry shortly");
  }

  try {
    const plan = options.plan ?? (await createProfileRepairPlan(options.paths));

    const revisionId = await commitLocalChanges({
      paths: options.paths,
      root: options.paths.profileDirectory,
      kind: "profile",
      updates: plan.updates,
    });

    await removeEmptyLegacyDirectories({ paths: options.paths, plan });

    return { revisionId, plan };
  } finally {
    lock.release();
  }
}
