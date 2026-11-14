import path from "node:path";
import { lstat } from "node:fs/promises";
import type { FileUpdate } from "@shadowclone/changes";
import {
  assertRegularDestination,
  fingerprint,
  readLocalFile,
} from "@shadowclone/core";
import type { EnvironmentArtifact, EnvironmentState } from "./types";

export async function publishSkillResources(options: {
  readonly source: string;
  readonly destinations: readonly string[];
  readonly state: EnvironmentState;
  readonly scope: string;
  readonly name: string;
}): Promise<{
  readonly updates: readonly FileUpdate[];
  readonly artifacts: readonly EnvironmentArtifact[];
}> {
  const updates: FileUpdate[] = [];
  const artifacts: EnvironmentArtifact[] = [];
  let bytes = 0;

  assertRegularDestination(path.join(options.source, "SKILL.md"));

  for await (const relativePath of new Bun.Glob("**/*").scan({
    cwd: options.source,
    dot: true,
    onlyFiles: false,
    followSymlinks: false,
  })) {
    const sourcePath = path.join(options.source, relativePath);
    const metadata = await lstat(sourcePath);

    if (
      metadata.isSymbolicLink() ||
      relativePath.split(path.sep).includes(".git")
    ) {
      throw new Error(
        "Skill resources cannot contain symbolic links or Git metadata",
      );
    }

    if (metadata.isDirectory() || relativePath === "SKILL.md") {
      continue;
    }

    if (!metadata.isFile()) {
      throw new Error("Skill resource must be a regular file");
    }

    bytes += metadata.size;

    if (bytes > 512_000) {
      throw new Error(
        "Skill resources exceed the reversible publication budget",
      );
    }

    const content = await readLocalFile({
      filePath: sourcePath,
      encoding: "base64",
    });

    if (content === null) {
      throw new Error("Skill resource disappeared during publication");
    }

    for (const destination of options.destinations) {
      const filePath = path.join(path.dirname(destination), relativePath);

      if (filePath === sourcePath) {
        continue;
      }

      const previous = await readLocalFile({ filePath, encoding: "base64" });
      const tracked = options.state.artifacts.find(
        (artifact) => artifact.filePath === filePath,
      );

      const unedited =
        tracked !== undefined && previous !== null && fingerprint(previous) === tracked.fingerprint;

      if (previous !== null && previous !== content && !unedited) {
        throw new Error(
          "Skill resource copies disagree; reconcile them before publication",
        );
      }

      updates.push({
        filePath,
        previous,
        next: content,
        encoding: "base64",
        mode: metadata.mode & 0o777,
      });
      artifacts.push({
        filePath,
        original: tracked ? tracked.original : previous,
        fingerprint: fingerprint(content),
        encoding: "base64",
        kind: "resource",
        scope: options.scope,
        name: options.name,
        description: "Supporting skill resource",
        learningKeys: [],
      });
    }
  }

  return { updates, artifacts };
}
