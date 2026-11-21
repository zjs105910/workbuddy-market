import type { ProjectPaths } from "@shadowclone/core";
import { resolveRedacted } from "@shadowclone/sessions";
import { revisionPath } from "./store";

export { commitLocalChanges, revisionTarget } from "./apply";
export { listRevisions } from "./store";
export { readRevision } from "./store";
export type { FileUpdate, LocalRevision } from "./types";

export async function showRevision(options: {
  readonly paths: ProjectPaths;
  readonly id: string;
}): Promise<string> {
  const sourcePath = revisionPath(options);
  const file = Bun.file(sourcePath);

  if (!(await file.exists())) {
    throw new Error("Revision was not found");
  }

  return resolveRedacted({
    ref: { type: "file", sourcePath, byteOffset: 0, byteLength: file.size },
  });
}
