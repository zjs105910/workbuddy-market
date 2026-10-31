import path from "node:path";
import { readBoundedFile } from "@shadowclone/core";
import { treeManifest } from "../files";
import type { ChangedFile } from "../receipt";

export type WorkspaceSnapshot = ReadonlyMap<string, { readonly hash: string; readonly content: string | null }>;

export async function snapshotWorkspace(directory: string): Promise<WorkspaceSnapshot> {
  const snapshot = new Map<string, { hash: string; content: string | null }>();

  for (const entry of await treeManifest({ directory })) {
    const content = await readBoundedFile({ filePath: path.join(directory, entry.path), roots: [directory], maximumBytes: 1_000_000 });
    snapshot.set(entry.path, { hash: entry.hash, content });
  }

  return snapshot;
}

export function changedFiles(options: { before: WorkspaceSnapshot; after: WorkspaceSnapshot }): ChangedFile[] {
  const files: ChangedFile[] = [];
  let bytes = 0;

  for (const relative of new Set([...options.before.keys(), ...options.after.keys()])) {
    const previous = options.before.get(relative);
    const next = options.after.get(relative);

    if (previous?.hash === next?.hash) {
      continue;
    }

    if ((previous && previous.content === null) || (next && next.content === null)) {
      throw new Error("Changed-file evidence is missing, binary, or oversized");
    }

    bytes += Buffer.byteLength(previous?.content ?? "") + Buffer.byteLength(next?.content ?? "");

    if (bytes > 2_000_000) {
      throw new Error("Candidate evidence exceeds the grading limit");
    }

    files.push({ path: relative, before: previous?.content ?? null, after: next?.content ?? null });
  }

  return files.toSorted((left, right) => left.path.localeCompare(right.path));
}
