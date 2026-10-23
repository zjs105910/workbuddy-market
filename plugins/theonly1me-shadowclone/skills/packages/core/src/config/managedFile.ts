import { constants } from "node:fs";
import { lstat, open } from "node:fs/promises";
import path from "node:path";

const otherWriteBits = 0o022;

export type PathStats = {
  readonly uid: number;
  readonly mode: number;
  readonly isFile: boolean;
  readonly isDirectory: boolean;
  readonly isSymbolicLink: boolean;
};

export function managedPathAncestors(filePath: string): readonly string[] {
  const directories: string[] = [];
  let current = path.dirname(filePath);

  while (true) {
    directories.push(current);

    const parent = path.dirname(current);

    if (parent === current) {
      return directories;
    }

    current = parent;
  }
}

export function managedStatsFailure(options: {
  readonly directories: readonly PathStats[];
  readonly file: PathStats;
}): string | null {
  for (const directory of options.directories) {
    if (directory.isSymbolicLink) {
      return "Managed policy path must not contain a symbolic link";
    }

    if (!directory.isDirectory) {
      return "Managed policy path must be a chain of directories";
    }

    if (directory.uid !== 0) {
      return "Managed policy must sit under root-owned directories";
    }

    if ((directory.mode & otherWriteBits) !== 0) {
      return "Managed policy directories must not be writable by other users";
    }
  }

  if (options.file.isSymbolicLink) {
    return "Managed policy must not be a symbolic link";
  }

  if (!options.file.isFile) {
    return "Managed policy must be a regular file";
  }

  if (options.file.uid !== 0) {
    return "Managed policy must be owned by root";
  }

  if ((options.file.mode & otherWriteBits) !== 0) {
    return "Managed policy must not be writable by other users";
  }

  return null;
}

function toPathStats(stats: {
  readonly uid: number;
  readonly mode: number;
  isFile: () => boolean;
  isDirectory: () => boolean;
  isSymbolicLink: () => boolean;
}): PathStats {
  return {
    uid: stats.uid,
    mode: stats.mode,
    isFile: stats.isFile(),
    isDirectory: stats.isDirectory(),
    isSymbolicLink: stats.isSymbolicLink(),
  };
}

export async function readRootOwnedFile(filePath: string): Promise<string> {
  const directories = await Promise.all(
    managedPathAncestors(filePath).map(async (directory) =>
      toPathStats(await lstat(directory)),
    ),
  );
  const link = toPathStats(await lstat(filePath));

  const handle = await open(
    filePath,
    constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK,
  );

  try {
    const opened = toPathStats(await handle.stat());
    const failure = managedStatsFailure({
      directories,
      file: link.isSymbolicLink ? link : opened,
    });

    if (failure !== null) {
      throw new Error(failure);
    }

    const buffer = Buffer.alloc(1024 * 1024 + 1);
    const read = await handle.read(buffer, 0, buffer.length, 0);

    if (read.bytesRead > 1024 * 1024) {
      throw new Error("Managed policy exceeds the size limit");
    }

    return buffer.subarray(0, read.bytesRead).toString("utf8");
  } finally {
    await handle.close();
  }
}
