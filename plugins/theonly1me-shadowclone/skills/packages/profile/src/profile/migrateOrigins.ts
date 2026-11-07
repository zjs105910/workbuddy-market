import { lstat, readdir, rename, rm } from "node:fs/promises";
import path from "node:path";
import { readBoundedFile, safeFilePath, maximumTextBytes, ownedWrite } from "@shadowclone/core";
import { originDirectoryName } from "@shadowclone/sessions";

function legacyIdentity(directory: string): string | null {
  const [host, owner, extra] = directory.split("--");

  if (
    extra !== undefined ||
    !owner ||
    !["github.com", "gitlab.com"].includes(host ?? "") ||
    !/^[a-z0-9][a-z0-9._-]*$/.test(owner)
  ) {
    return null;
  }

  return `${host}/${owner}`;
}

export async function migrateOriginProfiles(profileDirectory: string): Promise<{
  readonly migrated: number;
  readonly isolated: number;
}> {
  const root = path.join(profileDirectory, "org");

  if (
    (await safeFilePath({ filePath: root, roots: [profileDirectory] })) === null
  ) {
    return { migrated: 0, isolated: 0 };
  }

  const entries = await readdir(root, { withFileTypes: true });
  const journalPath = path.join(profileDirectory, ".origin-migration");
  const pending = await readBoundedFile({
    filePath: journalPath,
    roots: [profileDirectory],
    maximumBytes: 256,
  });
  const names = new Set<string>();

  if (pending !== null && legacyIdentity(pending) !== null) {
    names.add(pending);
  }

  for (const entry of entries.filter((entry) => entry.isDirectory())) {
    names.add(entry.name);
  }

  let migrated = 0;
  let isolated = 0;

  for (const name of names) {
    if (name.startsWith("isolated--") || /--[a-f0-9]{16}$/.test(name)) {
      continue;
    }

    const identity = legacyIdentity(name);

    if (identity === null) {
      isolated += 1;

      continue;
    }

    const nextName = originDirectoryName(identity);
    const target = path.join(root, nextName);
    const source = path.join(root, name);
    const sourceExists = await lstat(source).catch(() => null);

    if (
      (await lstat(target).catch(() => null)) &&
      (sourceExists !== null || pending !== name)
    ) {
      isolated += 1;

      continue;
    }

    const previousPrefix = `org/${name}/`;
    const nextPrefix = `org/${nextName}/`;
    const states: { filePath: string; text: string }[] = [];

    for (const name of [".generated", ".rejected"]) {
      const filePath = path.join(profileDirectory, name);
      const text = await readBoundedFile({
        filePath,
        roots: [profileDirectory],
        maximumBytes: maximumTextBytes,
      });

      if (text === null && (await lstat(filePath).catch(() => null))) {
        throw new Error(
          "Origin migration requires readable regular state files within the size limit",
        );
      }

      if (text !== null) {
        states.push({
          filePath,
          text: text
            .replaceAll(
              `"relativePath":"${previousPrefix}`,
              `"relativePath":"${nextPrefix}`,
            )
            .replaceAll(`\n${previousPrefix}`, `\n${nextPrefix}`)
            .replace(
              new RegExp(
                `^${previousPrefix.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`,
              ),
              nextPrefix,
            ),
        });
      }
    }

    await ownedWrite({ path: journalPath, content: name });

    if (sourceExists !== null) {
      await rename(source, target);
    }

    for (const state of states) {
      await ownedWrite({ path: state.filePath, content: state.text });
    }

    await rm(journalPath);
    migrated += 1;
  }

  return { migrated, isolated };
}
