import { lstat, mkdir, realpath, readlink, readdir } from "node:fs/promises";
import path from "node:path";
import { canonicalPath } from "@shadowclone/core";
import { fingerprint } from "../shared/structured";
import { relativePathSchema, type FrozenFile } from "./schema";

export async function requirePrivateDirectory(directory: string): Promise<string> {
  const resolved = canonicalPath(directory);
  let ancestor = resolved;

  while (true) {
    if (await lstat(path.join(ancestor, ".git")).catch(() => null)) {
      throw new Error("Private evaluation storage cannot be inside a repository");
    }

    const parent = path.dirname(ancestor);

    if (parent === ancestor) {
      return resolved;
    }

    ancestor = parent;
  }
}

export function confinedPath(options: { directory: string; relative: string }): string {
  relativePathSchema.parse(options.relative);
  return path.join(options.directory, options.relative);
}

export async function writeFrozenFile(options: { directory: string; file: FrozenFile }): Promise<void> {
  const target = confinedPath({ directory: options.directory, relative: options.file.path });
  const root = await realpath(options.directory);
  const destination = canonicalPath(path.dirname(target));

  if (destination !== root && !destination.startsWith(`${root}${path.sep}`)) {
    throw new Error("Frozen file destination escapes its private root");
  }

  await mkdir(path.dirname(target), { recursive: true, mode: 0o700 });
  const parent = await realpath(path.dirname(target));
  const existing = await lstat(target).catch(() => null);

  if ((parent !== root && !parent.startsWith(`${root}${path.sep}`)) || existing?.isSymbolicLink() || existing?.isDirectory()) {
    throw new Error("Frozen file destination escapes its private root");
  }

  await Bun.write(target, options.file.encoding === "base64"
    ? Buffer.from(options.file.content, "base64") : options.file.content,
    { mode: options.file.mode });
}

export type TreeEntry = { readonly path: string; readonly hash: string; readonly mode: number };

export async function treeManifest(options: {
  readonly directory: string;
  readonly includeDependencies?: boolean;
}): Promise<readonly TreeEntry[]> {
  const entries: TreeEntry[] = [];
  const directory = await realpath(options.directory);

  async function walk(relative: string): Promise<void> {
    const names = await readdir(path.join(directory, relative));

    for (const name of names.sort()) {
      if (name === ".git" || (!options.includeDependencies && name === "node_modules")) {
        continue;
      }

      const filePath = path.join(relative, name);
      const absolute = path.join(directory, filePath);
      const metadata = await lstat(absolute);

      if (metadata.isDirectory()) {
        await walk(filePath);
      } else if (metadata.isSymbolicLink()) {
        const target = await realpath(absolute);

        if (!target.startsWith(`${directory}${path.sep}`)) {
          throw new Error("Snapshot link escapes its private root");
        }

        entries.push({ path: filePath, hash: fingerprint(await readlink(absolute)), mode: metadata.mode });
      } else if (metadata.isFile()) {
        const hash = new Bun.CryptoHasher("sha256").update(await Bun.file(absolute).arrayBuffer()).digest("hex");
        entries.push({ path: filePath, hash, mode: metadata.mode });
      } else {
        throw new Error("Snapshot contains an unsupported entry");
      }
    }
  }

  await walk("");
  return entries;
}

export async function treeFingerprint(directory: string): Promise<string> {
  return fingerprint(await treeManifest({ directory, includeDependencies: true }));
}
