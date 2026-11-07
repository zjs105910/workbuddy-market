import { fingerprint, readLocalFile } from "@shadowclone/core";
import type { BuildDefinition, EnvironmentState } from "@shadowclone/environment";
import type { FileUpdate } from "@shadowclone/changes";

export async function retireBuildSkills(options: {
  readonly state: EnvironmentState;
  readonly build: BuildDefinition;
  readonly retained: ReadonlySet<string>;
}): Promise<{
  readonly state: EnvironmentState;
  readonly updates: readonly FileUpdate[];
  readonly warnings: readonly string[];
}> {
  const updates: FileUpdate[] = [];
  const removed = new Set<string>();
  const warnings: string[] = [];

  for (const artifact of options.state.artifacts) {
    if (
      artifact.buildId !== options.build.id ||
      (artifact.kind !== "skill" && artifact.kind !== "resource") ||
      options.retained.has(artifact.buildEntryId ?? "")
    ) {
      continue;
    }

    const encoding = artifact.kind === "resource" ? "base64" : "utf8";
    const previous = await readLocalFile({ filePath: artifact.filePath, encoding });

    if (previous !== null && fingerprint(previous) !== artifact.fingerprint) {
      warnings.push(
        `Preserved an externally edited copy of ${artifact.name}; it remains discoverable by its harness.`,
      );

      continue;
    }

    updates.push({
      filePath: artifact.filePath,
      previous,
      next: artifact.original,
      ...(artifact.kind === "resource" ? { encoding: "base64" as const } : {}),
    });
    removed.add(artifact.filePath);
  }

  return {
    state: {
      ...options.state,
      artifacts: options.state.artifacts.filter(
        (artifact) => !removed.has(artifact.filePath),
      ),
    },
    updates,
    warnings: [...new Set(warnings)],
  };
}
