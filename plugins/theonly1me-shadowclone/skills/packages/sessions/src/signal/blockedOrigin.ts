import type { RepositoryIdentity } from "./types";

function matchesPattern(value: string, pattern: string): boolean {
  const expression = pattern
    .split("*")
    .map((part) => part.replace(/[.+?^${}()|[\]\\]/g, "\\$&"))
    .join(".*");

  return new RegExp(`^${expression}$`).test(value);
}

export function isOriginBlocked(options: {
  readonly repository: RepositoryIdentity;
  readonly patterns: readonly string[];
}): boolean {
  if (options.patterns.length === 0) {
    return false;
  }

  const values = [
    ...new Set([options.repository.origin.id, options.repository.id]),
  ];

  return options.patterns.some((pattern) =>
    values.some((value) => matchesPattern(value, pattern)),
  );
}
