import type { ProfileImportReference } from "./types";

export function mergeProfileImportReference(options: {
  readonly stored: ProfileImportReference;
  readonly incoming: ProfileImportReference;
}): ProfileImportReference {
  return {
    repositoryAliases: [
      ...new Set([
        ...options.stored.repositoryAliases,
        ...options.incoming.repositoryAliases,
      ]),
    ].sort(),
    sourceLocator: options.incoming.sourceLocator,
  };
}
