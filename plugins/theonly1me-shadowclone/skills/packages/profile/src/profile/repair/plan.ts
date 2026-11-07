import { planOrigin } from "./originPlan";
import { readLocalText } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";
import { readGeneratedProfileState, readProfileRejections } from "../state";
import {
  renderGeneratedProfileState,
  renderProfileRejections,
} from "../stateRender";
import { discoverOriginRepairs } from "./discover";
import type {
  BlockedOriginRepair,
  OriginRepair,
  ProfileRepairPlan,
} from "./types";

function rewriteRelativePath(options: {
  readonly relativePath: string;
  readonly repairs: readonly {
    readonly sourceDirectory: string;
    readonly targetDirectory: string;
  }[];
}): string {
  for (const repair of options.repairs) {
    const sourcePrefix = `org/${repair.sourceDirectory}/`;

    if (options.relativePath.startsWith(sourcePrefix)) {
      return `org/${repair.targetDirectory}/${options.relativePath.slice(sourcePrefix.length)}`;
    }
  }

  return options.relativePath;
}

export async function createProfileRepairPlan(
  paths: ProjectPaths,
): Promise<ProfileRepairPlan> {
  const discovered = await discoverOriginRepairs(paths.profileDirectory);
  const repairs: OriginRepair[] = [];
  const blocked: BlockedOriginRepair[] = [];
  const updates: ProfileRepairPlan["updates"][number][] = [];

  for (const legacy of discovered.legacy) {
    const planned = await planOrigin({ paths, ...legacy });

    if (planned.blocked) {
      blocked.push(planned.blocked);
    }

    if (planned.repair) {
      repairs.push(planned.repair);
    }

    updates.push(...planned.updates);
  }

  const safeRepairs = discovered.legacy.filter(
    (legacy) =>
      !blocked.some(
        (entry) => entry.sourceDirectory === legacy.sourceDirectory,
      ),
  );

  const previousManifest = await readLocalText(paths.profileManifestFile);

  if (previousManifest !== null) {
    const entries = await readGeneratedProfileState(paths.profileManifestFile);

    const next = renderGeneratedProfileState(
      entries.map((entry) => ({
        ...entry,
        relativePath: rewriteRelativePath({
          relativePath: entry.relativePath,
          repairs: safeRepairs,
        }),
      })),
    );

    updates.push({
      filePath: paths.profileManifestFile,
      previous: previousManifest,
      next,
    });
  }

  const previousRejections = await readLocalText(paths.rejectedProfileFile);

  if (previousRejections !== null) {
    const entries = await readProfileRejections(paths.rejectedProfileFile);

    const next = renderProfileRejections(
      entries.map((entry) => ({
        ...entry,
        relativePath: rewriteRelativePath({
          relativePath: entry.relativePath,
          repairs: safeRepairs,
        }),
      })),
    );

    updates.push({
      filePath: paths.rejectedProfileFile,
      previous: previousRejections,
      next,
    });
  }

  return {
    repairs,
    blocked,
    isolatedDirectories: discovered.isolatedDirectories,
    legacyDirectories: discovered.legacy.length,
    updates,
  };
}
