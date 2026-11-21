import path from "node:path";
import { listRevisions, readRevision } from "@shadowclone/changes";
import {
  type BuildContext,
  type BuildScope,
  environmentFile,
  readEnvironment,
} from "@shadowclone/environment";
import { readLocalText } from "@shadowclone/core";
import { buildIdentity } from "./selection";

export async function lastBuildRevision(
  options: BuildContext & { readonly scope: BuildScope },
): Promise<string | null> {
  const state = await readEnvironment(options.paths);
  const id = buildIdentity(options);

  if (!state?.builds.some((build) => build.id === id)) {
    return null;
  }

  const current = await readLocalText(environmentFile(options.paths));
  const files = new Set(
    state.artifacts
      .filter((artifact) => artifact.buildId === id)
      .map((artifact) => artifact.filePath),
  );
  const history = await listRevisions(options.paths);

  for (const entry of history) {
    if (entry.kind !== "environment" || entry.status !== "applied") {
      continue;
    }

    const revision = await readRevision({ paths: options.paths, id: entry.id });
    const environment = revision.changes.find(
      (change) =>
        path.resolve(revision.root, change.relativePath) ===
        environmentFile(options.paths),
    );

    if (environment?.after !== current) {
      return null;
    }

    if (
      revision.changes.some((change) =>
        files.has(path.resolve(revision.root, change.relativePath)),
      )
    ) {
      return revision.id;
    }
  }

  return null;
}
