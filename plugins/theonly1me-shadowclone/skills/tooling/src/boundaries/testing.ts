import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { readImports } from "./imports";
import type { WorkspaceKey, WorkspaceManifest } from "./manifests";

export function edgesOf(files: Record<string, string>) {
  return Object.entries(files).flatMap(([file, text]) => readImports({ file, text }));
}

export async function treeWith(files: Record<string, string>): Promise<string> {
  const rootDirectory = await mkdtemp(path.join(os.tmpdir(), "shadowclone-boundaries-"));

  for (const [file, text] of Object.entries(files)) {
    await Bun.write(path.join(rootDirectory, file), text);
  }

  return rootDirectory;
}

export function manifestOf(options: {
  readonly key: WorkspaceKey;
  readonly exportedSubpaths?: readonly string[];
  readonly workspaceDependencies?: readonly string[];
}): [WorkspaceKey, WorkspaceManifest] {
  return [
    options.key,
    {
      file: `${options.key}/package.json`,
      name: `@shadowclone/${options.key}`,
      version: null,
      isPrivate: true,
      exportedSubpaths: options.exportedSubpaths ?? ["."],
      workspaceDependencies: options.workspaceDependencies ?? [],
    },
  ];
}
