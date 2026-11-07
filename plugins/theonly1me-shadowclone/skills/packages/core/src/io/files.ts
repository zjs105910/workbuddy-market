import { constants } from "node:fs";
import { lstat, open, realpath } from "node:fs/promises";
import path from "node:path";

export function containsPath(options: {
  readonly root: string;
  readonly target: string;
}): boolean {
  const relative = path.relative(options.root, options.target);

  return (
    relative === "" ||
    (!relative.startsWith(`..${path.sep}`) &&
      relative !== ".." &&
      !path.isAbsolute(relative))
  );
}

export async function safeFilePath(options: {
  readonly filePath: string;
  readonly roots: readonly string[];
}): Promise<string | null> {
  if (!path.isAbsolute(options.filePath)) {
    return null;
  }

  const canonical = await realpath(options.filePath).catch(() => null);

  if (canonical === null) {
    return null;
  }

  for (const root of options.roots) {
    if (
      !containsPath({
        root: path.resolve(root),
        target: path.resolve(options.filePath),
      })
    ) {
      continue;
    }

    const canonicalRoot = await realpath(root).catch(() => null);

    if (
      canonicalRoot === null ||
      !containsPath({ root: canonicalRoot, target: canonical })
    ) {
      continue;
    }

    let current = path.resolve(options.filePath);

    while (true) {
      const stats = await lstat(current);

      if (stats.isSymbolicLink()) {
        return null;
      }

      if (current === path.resolve(root)) {
        return canonical;
      }

      current = path.dirname(current);
    }
  }

  return null;
}

export async function readBoundedFile(options: {
  readonly filePath: string;
  readonly roots: readonly string[];
  readonly maximumBytes: number;
  readonly offset?: number;
  readonly length?: number;
  readonly fileIdentity?: string;
  readonly contentHash?: string;
}): Promise<string | null> {
  const filePath = await safeFilePath(options);

  if (filePath === null) {
    return null;
  }

  const handle = await open(
    filePath,
    constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK,
  );

  try {
    const before = await handle.stat();

    if (
      options.fileIdentity !== undefined &&
      options.fileIdentity !== `${before.dev}:${before.ino}`
    ) {
      return null;
    }

    const offset = options.offset ?? 0;
    const length = options.length ?? before.size;

    if (
      !before.isFile() ||
      !Number.isSafeInteger(offset) ||
      offset < 0 ||
      !Number.isSafeInteger(length) ||
      length < 0 ||
      length > options.maximumBytes ||
      !Number.isSafeInteger(offset + length) ||
      offset + length > before.size
    ) {
      return null;
    }

    const bytes = Buffer.alloc(length);
    let total = 0;

    while (total < length) {
      const result = await handle.read(
        bytes,
        total,
        length - total,
        offset + total,
      );

      if (result.bytesRead === 0) {
        return null;
      }

      total += result.bytesRead;
    }

    if (
      options.contentHash !== undefined &&
      new Bun.CryptoHasher("sha256").update(bytes).digest("hex") !==
        options.contentHash
    ) {
      return null;
    }

    const after = await handle.stat();

    return before.mtimeMs === after.mtimeMs && before.size === after.size
      ? bytes.toString("utf8")
      : null;
  } finally {
    await handle.close();
  }
}
