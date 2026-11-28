import { lstatSync, readlinkSync } from "node:fs";
import { mkdir, open, rename, rm } from "node:fs/promises";
import path from "node:path";
import { removeEmptySkillFolders } from "./skillFolders";

export { firstLink, linkedHomeFile, realPathOrNull, resolvedPath } from "./links";
export { acquireLocalLock } from "./lock";

export function fingerprint(text: string): string {
  return new Bun.CryptoHasher("sha256").update(text).digest("hex");
}

export class UnsafeDestinationError extends Error {
  readonly path: string;
  readonly target: string | null;

  constructor(path: string, target: string | null) {
    super(
      `Destination must be a regular file without symbolic links: ${path}${
        target === null ? "" : ` (a link to ${target})`
      }`,
    );
    this.path = path;
    this.target = target;
  }
}

export function assertRegularDestination(filePath: string): void {
  let current = path.resolve(filePath);

  for (;;) {
    const metadata = lstatSync(current, { throwIfNoEntry: false });

    if (
      metadata?.isSymbolicLink() ||
      (current === path.resolve(filePath) && metadata && !metadata.isFile())
    ) {
      throw new UnsafeDestinationError(
        current,
        metadata?.isSymbolicLink() ? readlinkSync(current) : null,
      );
    }

    const parent = path.dirname(current);

    if (parent === current) {
      return;
    }

    current = parent;
  }
}

export async function readLocalText(filePath: string): Promise<string | null> {
  return readLocalFile({ filePath });
}

export async function readLocalFile(options: {
  readonly filePath: string;
  readonly encoding?: "utf8" | "base64";
}): Promise<string | null> {
  const { filePath } = options;

  assertRegularDestination(filePath);

  const file = Bun.file(filePath);

  if (!(await file.exists())) {
    return null;
  }

  if (file.size > 2_000_000) {
    throw new Error("Local file exceeds the supported size");
  }

  return options.encoding === "base64"
    ? Buffer.from(await file.arrayBuffer()).toString("base64")
    : file.text();
}

export async function replaceLocalText(options: {
  readonly filePath: string;
  readonly previous: string | null;
  readonly next: string | null;
  readonly encoding?: "utf8" | "base64";
  readonly mode?: number;
}): Promise<void> {
  if ((await readLocalFile(options)) !== options.previous) {
    throw new Error(
      "Destination changed during the update; retry after reviewing it",
    );
  }

  if (options.next === options.previous) {
    return;
  }

  if (options.next === null) {
    await rm(options.filePath, { force: true });
    await removeEmptySkillFolders(options.filePath);

    return;
  }

  await mkdir(path.dirname(options.filePath), { recursive: true });

  const temporary = `${options.filePath}.${crypto.randomUUID()}.tmp`;

  try {
    const mode = lstatSync(options.filePath, { throwIfNoEntry: false })?.mode;
    const handle = await open(
      temporary,
      "wx",
      mode === undefined ? (options.mode ?? 0o600) : mode & 0o777,
    );

    try {
      await handle.writeFile(
        options.encoding === "base64"
          ? Buffer.from(options.next, "base64")
          : options.next,
      );
    } finally {
      await handle.close();
    }

    if ((await readLocalFile(options)) !== options.previous) {
      throw new Error(
        "Destination changed during the update; retry after reviewing it",
      );
    }

    await rename(temporary, options.filePath);
  } finally {
    await rm(temporary, { force: true });
  }
}
