import { readdir, rmdir } from "node:fs/promises";
import path from "node:path";
import { commitLocalChanges } from "@shadowclone/changes";
import { acquireLocalLock } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";
import type { ProfileCurationDecisions } from "./decisions";
import {
  createProfileCurationPlan,
  type ProfileCurationPlan,
} from "./curationPlan";

type ApplyProfileCurationOptions =
  | {
      readonly paths: ProjectPaths;
      readonly decisions: ProfileCurationDecisions;
    }
  | {
      readonly paths: ProjectPaths;
      readonly plan: ProfileCurationPlan;
    };

async function removeEmptyIsolatedDirectories(
  profileDirectory: string,
): Promise<void> {
  for (const root of ["org", path.join("references", "org")]) {
    const directory = path.join(profileDirectory, root);
    const entries = await readdir(directory, { withFileTypes: true }).catch(
      () => [],
    );

    for (const entry of entries) {
      if (!entry.isDirectory() || !entry.name.startsWith("isolated--")) {
        continue;
      }

      const isolated = path.join(directory, entry.name);

      await rmdir(path.join(isolated, "projects")).catch(() => undefined);
      await rmdir(isolated).catch(() => undefined);
    }
  }
}

export async function applyProfileCuration(
  options: ApplyProfileCurationOptions,
): Promise<{
  readonly revisionId: string | null;
  readonly plan: ProfileCurationPlan;
}> {
  const lock = await acquireLocalLock(
    path.join(options.paths.shadowcloneDirectory, "profile-write.db"),
  );

  if (!lock) {
    throw new Error("Another profile update is running; retry shortly");
  }

  try {
    const plan =
      "plan" in options
        ? options.plan
        : await createProfileCurationPlan({
            paths: options.paths,
            decisions: options.decisions,
          });

    const revisionId = await commitLocalChanges({
      paths: options.paths,
      root: options.paths.profileDirectory,
      kind: "profile",
      updates: plan.updates,
    });

    await removeEmptyIsolatedDirectories(options.paths.profileDirectory);

    return { revisionId, plan };
  } finally {
    lock.release();
  }
}
