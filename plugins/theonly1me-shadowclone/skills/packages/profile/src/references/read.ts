import { redactReference } from "./redactedRecord";
import { stat } from "node:fs/promises";
import path from "node:path";
import { readBoundedFile } from "@shadowclone/core";
import type { OriginScope } from "@shadowclone/sessions";
import { parseReference } from "./format";
import { referenceMatchesPath, referenceScopeRoots } from "./paths";
import type { ReferenceSearchResult } from "./types";

export const maximumReferenceBytes = 64 * 1024;

async function readReference(options: {
  readonly profileDirectory: string;
  readonly relativePath: string;
}): Promise<ReferenceSearchResult | null> {
  const filePath = path.join(options.profileDirectory, options.relativePath);
  const size = await stat(filePath)
    .then((value) => value.size)
    .catch(() => 0);

  if (size < 1 || size > maximumReferenceBytes) {
    return null;
  }

  const raw = await readBoundedFile({
    filePath,
    roots: [options.profileDirectory],
    maximumBytes: maximumReferenceBytes,
  });

  if (raw === null) {
    return null;
  }

  const parsed = parseReference(raw);

  if (parsed === null) {
    return null;
  }

  const record = await redactReference({
    record: parsed,
    filePath,
    root: options.profileDirectory,
    raw,
  });

  return record !== null &&
    referenceMatchesPath({ record, relativePath: options.relativePath })
    ? { record, relativePath: options.relativePath }
    : null;
}

async function scopedPaths(options: {
  readonly profileDirectory: string;
  readonly origin: OriginScope | null;
  readonly targetRepo: string | null;
  readonly scope?: "global" | "scoped" | "combined";
}): Promise<readonly string[]> {
  const paths: string[] = [];

  for (const root of referenceScopeRoots(options)) {
    const absoluteRoot = path.join(options.profileDirectory, root);
    const exists = await stat(absoluteRoot)
      .then((value) => value.isDirectory())
      .catch(() => false);

    if (!exists) {
      continue;
    }

    for await (const filePath of new Bun.Glob("*.md").scan({
      cwd: absoluteRoot,
      absolute: true,
      onlyFiles: true,
    })) {
      paths.push(path.relative(options.profileDirectory, filePath));
    }
  }

  return [...new Set(paths)].sort();
}

export async function readScopedReferences(options: {
  readonly profileDirectory: string;
  readonly origin: OriginScope | null;
  readonly targetRepo: string | null;
  readonly scope?: "global" | "scoped" | "combined";
}): Promise<readonly ReferenceSearchResult[]> {
  const results = await Promise.all(
    (await scopedPaths(options)).map((relativePath) =>
      readReference({
        profileDirectory: options.profileDirectory,
        relativePath,
      }),
    ),
  );

  return results.filter((result) => result !== null);
}
