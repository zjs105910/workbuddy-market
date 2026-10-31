import path from "node:path";
import { z } from "zod";
import {
  readLocalText,
  replaceLocalText,
  canonicalPath,
  type ProjectPaths,
} from "@shadowclone/core";

const rootsSchema = z.strictObject({
  version: z.literal(1),
  roots: z.array(z.string().min(1)),
});

function rootsPath(paths: ProjectPaths): string {
  return path.join(paths.shadowcloneDirectory, "harness-roots.json");
}

export async function readHarnessRoots(
  paths: ProjectPaths,
): Promise<readonly string[]> {
  const text = await readLocalText(rootsPath(paths));

  if (text === null) {
    return [];
  }

  try {
    return rootsSchema.parse(JSON.parse(text)).roots;
  } catch {
    throw new Error("Invalid harness state");
  }
}

export async function recordHarnessRoot(options: {
  readonly paths: ProjectPaths;
  readonly root: string;
}): Promise<void> {
  const filePath = rootsPath(options.paths);
  const previous = await readLocalText(filePath);
  const roots = await readHarnessRoots(options.paths);
  const root = canonicalPath(options.root);

  if (roots.includes(root)) {
    return;
  }

  await replaceLocalText({
    filePath,
    previous,
    next: `${JSON.stringify({ version: 1, roots: [...roots, root].sort() }, null, 2)}\n`,
  });
}
