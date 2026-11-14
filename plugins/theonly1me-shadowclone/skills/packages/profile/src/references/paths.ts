import path from "node:path";
import type { OriginScope } from "@shadowclone/sessions";
import { isSafeProfileSegment } from "../profile/render";
import type { ReferenceRecord } from "./types";

export function referenceRelativePath(record: ReferenceRecord): string {
  if (!isSafeProfileSegment(record.key)) {
    throw new Error("Invalid reference key");
  }

  if (record.scope === "global") {
    return path.join("references", "global", `${record.key}.md`);
  }

  if (!isSafeProfileSegment(record.originDirectory)) {
    throw new Error("Invalid reference origin");
  }

  if (record.scope === "org") {
    return path.join(
      "references",
      "org",
      record.originDirectory,
      `${record.key}.md`,
    );
  }

  if (!isSafeProfileSegment(record.repositoryName)) {
    throw new Error("Invalid reference repository");
  }

  return path.join(
    "references",
    "org",
    record.originDirectory,
    "projects",
    record.repositoryName,
    `${record.key}.md`,
  );
}

export function referenceScopeRoots(options: {
  readonly origin: OriginScope | null;
  readonly targetRepo: string | null;
  readonly scope?: "global" | "scoped" | "combined";
}): readonly string[] {
  const roots: string[] = [];

  if (options.scope !== "scoped") {
    roots.push(path.join("references", "global"));
  }

  if (
    options.scope === "global" ||
    options.origin === null ||
    !isSafeProfileSegment(options.origin.directoryName)
  ) {
    return roots;
  }

  const organization = path.join(
    "references",
    "org",
    options.origin.directoryName,
  );

  roots.push(organization);

  if (options.targetRepo !== null && isSafeProfileSegment(options.targetRepo)) {
    roots.push(path.join(organization, "projects", options.targetRepo));
  }

  return roots;
}

export function referenceMatchesPath(options: {
  readonly record: ReferenceRecord;
  readonly relativePath: string;
}): boolean {
  return (
    path.normalize(referenceRelativePath(options.record)) ===
    path.normalize(options.relativePath)
  );
}
