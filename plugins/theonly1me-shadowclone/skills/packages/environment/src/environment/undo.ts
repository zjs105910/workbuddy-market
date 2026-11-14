import path from "node:path";
import {
  canonicalPath,
  type ProjectPaths,
  readLocalFile,
  acquireLocalLock,
} from "@shadowclone/core";
import { commitLocalChanges, readRevision, revisionTarget } from "@shadowclone/changes";
import { authorizedEnvironmentTarget } from "./authorization";

const lockNames = {
  profile: "profile-write.db",
  skill: "skills-worker.db",
  harness: "harness-write.db",
  environment: "environment-write.db",
} as const;
const harnessTarget =
  /^(?:AGENTS\.md|CLAUDE\.md|\.shadowclone\/harness\.json|\.claude\/settings\.local\.json|\.(?:agents|claude)\/skills\/[a-z0-9]+(?:-[a-z0-9]+)*\/.+)$/;

export async function undoRevision(options: {
  readonly paths: ProjectPaths;
  readonly id: string;
  readonly skillRoots?: readonly string[];
  readonly harnessRoots?: readonly string[];
}): Promise<string | null> {
  const revision = await readRevision(options);
  const lock = await acquireLocalLock(
    path.join(options.paths.shadowcloneDirectory, lockNames[revision.kind]),
  );

  if (!lock) {
    throw new Error("Another update is running; retry undo shortly");
  }

  try {
    const allowed =
      revision.kind === "profile"
        ? [canonicalPath(options.paths.profileDirectory)]
        : (
            (revision.kind === "skill"
              ? options.skillRoots
              : options.harnessRoots) ?? []
          ).map(canonicalPath);

    if (
      revision.kind !== "environment" &&
      !allowed.includes(canonicalPath(revision.root))
    ) {
      throw new Error("Revision root is not an authorized destination");
    }

    const updates = [];

    for (const change of revision.changes) {
      if (
        revision.kind === "skill" &&
        !change.relativePath.endsWith("/SKILL.md")
      ) {
        throw new Error("Invalid skill revision target");
      }

      if (
        revision.kind === "harness" &&
        !harnessTarget.test(change.relativePath.split(path.sep).join("/"))
      ) {
        throw new Error("Invalid harness revision target");
      }

      if (
        revision.kind === "profile" &&
        !(
          change.relativePath === ".generated" ||
          change.relativePath === ".rejected" ||
          /^(global|org|references\/(?:global|org))\/.+\.md$/.test(
            change.relativePath.split(path.sep).join("/"),
          ) ||
          /^migrations\/claude-memory-[a-f0-9]{16}\.json$/.test(
            change.relativePath.split(path.sep).join("/"),
          )
        )
      ) {
        throw new Error("Invalid profile revision target");
      }

      const filePath = revisionTarget({
        root: revision.root,
        relativePath: change.relativePath,
      });

      if (
        revision.kind === "environment" &&
        !(await authorizedEnvironmentTarget({ paths: options.paths, filePath }))
      ) {
        throw new Error(
          "Revision target is not an authorized environment destination",
        );
      }

      const current = await readLocalFile({
        filePath,
        encoding: change.encoding,
      });

      if (
        current !== change.after &&
        !(revision.status === "prepared" && current === change.before)
      ) {
        throw new Error(
          "Revision conflicts with subsequent edits; files were preserved",
        );
      }

      updates.push({
        filePath,
        next: change.before,
        previous: current,
        encoding: change.encoding,
        mode: change.mode,
      });
    }

    return await commitLocalChanges({
      paths: options.paths,
      root: revision.root,
      kind: revision.kind,
      updates,
    });
  } finally {
    lock.release();
  }
}
