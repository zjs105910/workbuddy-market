import { lstat, readdir } from "node:fs/promises";
import path from "node:path";

const maximumEntries = 500;
const maximumManifestBytes = 256_000;

export async function readRootEntries(
  root: string,
): Promise<readonly string[]> {
  const entries = await readdir(root).catch(() => {
    throw new Error("Repository root could not be listed");
  });

  if (entries.length > maximumEntries) {
    throw new Error("Repository root has too many entries to inspect");
  }

  return entries.filter((entry) => entry !== ".git").sort();
}

export async function readManifest(options: {
  readonly root: string;
  readonly relativePath: string;
}): Promise<string | null> {
  const filePath = path.join(options.root, options.relativePath);
  const metadata = await lstat(filePath).catch(() => null);

  if (metadata === null || metadata.isSymbolicLink() || !metadata.isFile()) {
    return null;
  }

  if (metadata.size > maximumManifestBytes) {
    throw new Error("A repository manifest is too large to inspect");
  }

  return Bun.file(filePath).text();
}

export async function readManifestDirectory(options: {
  readonly root: string;
  readonly relativePath: string;
  readonly extensions: readonly string[];
  readonly maximumFiles: number;
}): Promise<readonly string[]> {
  const directory = path.join(options.root, options.relativePath);
  const metadata = await lstat(directory).catch(() => null);

  if (
    metadata === null ||
    metadata.isSymbolicLink() ||
    !metadata.isDirectory()
  ) {
    return [];
  }

  const names = (await readdir(directory))
    .filter((name) =>
      options.extensions.some((extension) => name.endsWith(extension)),
    )
    .sort();
  const texts: string[] = [];

  for (const name of names.slice(0, options.maximumFiles)) {
    const text = await readManifest({
      root: options.root,
      relativePath: path.join(options.relativePath, name),
    });

    if (text !== null) {
      texts.push(text);
    }
  }

  return texts;
}
