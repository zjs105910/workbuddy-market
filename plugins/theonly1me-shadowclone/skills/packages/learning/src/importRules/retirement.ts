import type { GeneratedProfileStateEntry } from "@shadowclone/profile";

export function isRemovedImport(options: {
  readonly entry: GeneratedProfileStateEntry;
  readonly aliases: readonly string[];
  readonly currentLocators: ReadonlySet<string>;
}): boolean {
  const reference = options.entry.importReference;

  if (
    options.entry.disposition !== "present" ||
    options.entry.source === "user" ||
    reference === null
  ) {
    return false;
  }

  return (
    reference.repositoryAliases.some((alias) =>
      options.aliases.includes(alias),
    ) && !options.currentLocators.has(reference.sourceLocator)
  );
}
