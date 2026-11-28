import { readdir } from "node:fs/promises";
import path from "node:path";
import { originDirectoryName } from "@shadowclone/sessions";

export type LegacyOrigin = {
  readonly sourceDirectory: string;
  readonly targetDirectory: string;
  readonly originId: string;
};

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

async function directoryNames(root: string): Promise<readonly string[]> {
  try {
    return (await readdir(root, { withFileTypes: true }))
      .filter((entry) => entry.isDirectory())
      .map((entry) => entry.name);
  } catch {
    return [];
  }
}

export async function discoverOriginRepairs(profileDirectory: string): Promise<{
  readonly legacy: readonly LegacyOrigin[];
  readonly isolatedDirectories: number;
}> {
  const roots = [
    path.join(profileDirectory, "org"),
    path.join(profileDirectory, "references", "org"),
  ];
  const names = new Set((await Promise.all(roots.map(directoryNames))).flat());
  const isolatedDirectories = [...names].filter((name) =>
    name.startsWith("isolated--"),
  ).length;

  const legacy = [...names].flatMap((sourceDirectory) => {
    const originId = legacyIdentity(sourceDirectory);

    return originId === null
      ? []
      : [
          {
            sourceDirectory,
            targetDirectory: originDirectoryName(originId),
            originId,
          },
        ];
  });

  return {
    legacy: legacy.sort((left, right) =>
      left.sourceDirectory.localeCompare(right.sourceDirectory),
    ),
    isolatedDirectories,
  };
}
