import path from "node:path";
import {
  readLocalFile,
  replaceLocalText,
  canonicalPath,
  type ProjectPaths,
} from "@shadowclone/core";
import { storeRevision } from "./store";
import type { FileUpdate, LocalRevision } from "./types";

export function revisionTarget(options: {
  readonly root: string;
  readonly relativePath: string;
}): string {
  const root = canonicalPath(options.root);
  const target = path.resolve(root, options.relativePath);

  if (
    target === root ||
    !target.startsWith(root === path.sep ? root : `${root}${path.sep}`)
  ) {
    throw new Error("Revision target escapes its root");
  }

  return target;
}

export async function applyRevisionFiles(options: {
  readonly revision: LocalRevision;
  readonly reverse?: boolean;
  readonly replace?: typeof replaceLocalText;
}): Promise<void> {
  const changes = options.revision.changes.map((change) => ({
    filePath: revisionTarget({
      root: options.revision.root,
      relativePath: change.relativePath,
    }),
    previous: options.reverse ? change.after : change.before,
    next: options.reverse ? change.before : change.after,
    encoding: change.encoding,
    mode: change.mode,
  }));

  for (const change of changes) {
    if ((await readLocalFile(change)) !== change.previous) {
      throw new Error(
        "Revision conflicts with subsequent edits; files were preserved",
      );
    }
  }

  const completed: typeof changes = [];

  try {
    for (const change of changes) {
      await (options.replace ?? replaceLocalText)(change);
      completed.push(change);
    }
  } catch (error) {
    for (const change of completed.reverse()) {
      await replaceLocalText({
        ...change,
        previous: change.next,
        next: change.previous,
      });
    }

    throw error;
  }
}

export async function commitLocalChanges(options: {
  readonly paths: ProjectPaths;
  readonly root: string;
  readonly kind: LocalRevision["kind"];
  readonly updates: readonly FileUpdate[];
}): Promise<string | null> {
  const root = canonicalPath(options.root);
  const changes: LocalRevision["changes"] = [];

  for (const update of options.updates) {
    const relativePath = path.relative(root, update.filePath);
    const filePath = revisionTarget({ root, relativePath });
    const before = await readLocalFile({ filePath, encoding: update.encoding });

    if (update.previous !== undefined && before !== update.previous) {
      throw new Error(
        "Revision conflicts with subsequent edits; files were preserved",
      );
    }

    if (before !== update.next) {
      changes.push({
        relativePath,
        before,
        after: update.next,
        encoding: update.encoding,
        mode: update.mode,
      });
    }
  }

  if (changes.length === 0) {
    return null;
  }

  if (
    new Set(changes.map((change) => change.relativePath)).size !==
    changes.length
  ) {
    throw new Error("Revision contains duplicate destinations");
  }

  if (changes.length > 256) {
    throw new Error("Revision exceeds the supported file count");
  }

  const revision: LocalRevision = {
    id: crypto.randomUUID(),
    kind: options.kind,
    root,
    createdAt: Date.now(),
    status: "prepared",
    changes,
  };

  if (Buffer.byteLength(JSON.stringify(revision)) > 1_900_000) {
    throw new Error("Revision exceeds the supported history size");
  }

  await storeRevision({ paths: options.paths, revision });
  await applyRevisionFiles({ revision });
  await storeRevision({
    paths: options.paths,
    revision: { ...revision, status: "applied" },
  });

  return revision.id;
}
