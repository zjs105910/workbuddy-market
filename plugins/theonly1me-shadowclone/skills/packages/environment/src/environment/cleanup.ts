import { fingerprint, readLocalText, readLocalFile } from "@shadowclone/core";
import { managedSection } from "../integrations/markdown";
import type { ProjectPaths } from "@shadowclone/core";
import { readEnvironment, environmentFile } from "./store";
import { publishEnvironmentRevision } from "./revision";

export async function removeLearningEnvironment(
  paths: ProjectPaths,
): Promise<void> {
  const state = await readEnvironment(paths);

  if (state === null) {
    return;
  }

  const updates = [];

  for (const artifact of state.artifacts) {
    const previous = await readLocalFile(artifact);
    const observed =
      artifact.kind === "instructions"
        ? managedSection(previous ?? "")
        : previous;

    if (observed === null || fingerprint(observed) !== artifact.fingerprint) {
      throw new Error(
        "A maintained file changed; reconcile it before forgetting",
      );
    }

    const next =
      artifact.kind === "instructions" && previous !== null
        ? previous.replace(
            observed,
            managedSection(artifact.original ?? "") ?? "",
          )
        : artifact.original;

    updates.push({
      filePath: artifact.filePath,
      previous,
      next,
      encoding: artifact.encoding,
    });
  }

  updates.push({
    filePath: environmentFile(paths),
    previous: await readLocalText(environmentFile(paths)),
    next: null,
  });
  await publishEnvironmentRevision({ paths, updates });
}
