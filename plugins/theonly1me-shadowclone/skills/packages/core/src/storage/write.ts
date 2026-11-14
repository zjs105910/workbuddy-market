import { constants } from "node:fs";
import { lstat, mkdir, open, realpath, rename, rm } from "node:fs/promises";
import path from "node:path";

export const ownedDirectoryMode = 0o700;
export const ownedFileMode = 0o600;

async function checkedDirectory(directory: string): Promise<string> {
  const absolute = path.resolve(directory);
  const stats = await lstat(absolute).catch(() => null);

  if (stats === null) {
    const parent = await checkedDirectory(path.dirname(absolute));
    const target = path.join(parent, path.basename(absolute));

    await mkdir(target, { mode: ownedDirectoryMode, recursive: true });

    return checkedDirectory(target);
  }

  if (stats.isSymbolicLink()) {
    if (absolute === "/tmp" || absolute === "/var") {
      return realpath(absolute);
    }

    throw new Error("Storage directory must not be a symbolic link");
  }

  if (!stats.isDirectory()) {
    throw new Error("Storage parent must be a directory");
  }

  const parent = path.dirname(absolute);

  if (parent === absolute) {
    return absolute;
  }

  return path.join(await checkedDirectory(parent), path.basename(absolute));
}

export async function ownedDirectory(directory: string): Promise<void> {
  const canonical = await checkedDirectory(directory);
  const handle = await open(
    canonical,
    constants.O_RDONLY | constants.O_NOFOLLOW,
  );

  try {
    const stats = await handle.stat();

    if (stats.uid !== process.getuid?.()) {
      throw new Error("Storage directory must be owned by the current user");
    }

    await handle.chmod(ownedDirectoryMode);
  } finally {
    await handle.close();
  }
}

export async function ownedWrite(options: {
  readonly path: string;
  readonly content: string;
}): Promise<void> {
  const directory = path.dirname(options.path);

  await ownedDirectory(directory);

  const existing = await lstat(options.path).catch(() => null);

  if (existing && (!existing.isFile() || existing.isSymbolicLink())) {
    throw new Error("Storage target must be a regular file");
  }

  const temporaryPath = path.join(
    directory,
    `.${path.basename(options.path)}.${crypto.randomUUID()}.partial`,
  );

  try {
    const handle = await open(temporaryPath, "wx", ownedFileMode);

    try {
      await handle.writeFile(options.content);
      await handle.sync();
    } finally {
      await handle.close();
    }

    await rename(temporaryPath, options.path);
  } finally {
    await rm(temporaryPath, { force: true });
  }
}

export async function ownedFile(filePath: string): Promise<void> {
  const stats = await lstat(filePath).catch(() => null);

  if (stats === null) {
    return;
  }

  const handle = await open(
    filePath,
    constants.O_RDONLY | constants.O_NOFOLLOW,
  );

  try {
    const opened = await handle.stat();

    if (!opened.isFile() || opened.uid !== process.getuid?.()) {
      throw new Error("Storage file must be owned by the current user");
    }

    await handle.chmod(ownedFileMode);
  } finally {
    await handle.close();
  }
}
