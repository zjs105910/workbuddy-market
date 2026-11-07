import path from "node:path";
import { existsSync } from "node:fs";
import { z } from "zod";
import { readLocalText, replaceLocalText, ownedDirectory, ownedFile } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";
import { revisionSchema, type LocalRevision } from "./types";

export function revisionPath(options: {
  readonly paths: ProjectPaths;
  readonly id: string;
}): string {
  if (!z.uuid().safeParse(options.id).success) {
    throw new Error("Revision id must be a UUID");
  }

  return path.join(
    options.paths.shadowcloneDirectory,
    "history",
    `${options.id}.json`,
  );
}

export async function readRevision(options: {
  readonly paths: ProjectPaths;
  readonly id: string;
}): Promise<LocalRevision> {
  const text = await readLocalText(revisionPath(options));

  if (text === null) {
    throw new Error("Revision was not found");
  }

  try {
    return revisionSchema.parse(JSON.parse(text));
  } catch {
    throw new Error("Invalid revision record");
  }
}

export async function storeRevision(options: {
  readonly paths: ProjectPaths;
  readonly revision: LocalRevision;
}): Promise<void> {
  const filePath = revisionPath({
    paths: options.paths,
    id: options.revision.id,
  });

  await ownedDirectory(path.dirname(filePath));
  await ownedFile(filePath);
  await replaceLocalText({
    filePath,
    previous: await readLocalText(filePath),
    next: `${JSON.stringify(options.revision, null, 2)}\n`,
  });
}

export async function listRevisions(paths: ProjectPaths): Promise<
  readonly {
    readonly id: string;
    readonly kind: LocalRevision["kind"];
    readonly createdAt: number;
    readonly status: LocalRevision["status"];
    readonly files: number;
  }[]
> {
  const directory = path.join(paths.shadowcloneDirectory, "history");

  if (!existsSync(directory)) {
    return [];
  }

  const revisions = [];

  for await (const filename of new Bun.Glob("*.json").scan({
    cwd: directory,
    onlyFiles: true,
    throwErrorOnBrokenSymlink: true,
  })) {
    const revision = await readRevision({ paths, id: filename.slice(0, -5) });

    revisions.push({
      id: revision.id,
      kind: revision.kind,
      createdAt: revision.createdAt,
      status: revision.status,
      files: revision.changes.length,
    });
  }

  return revisions.sort((left, right) => right.createdAt - left.createdAt);
}
