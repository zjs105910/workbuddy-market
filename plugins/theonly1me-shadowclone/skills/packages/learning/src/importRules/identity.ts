import { canonicalPath } from "@shadowclone/core";
import type { ProfileImportReference } from "@shadowclone/profile";
import { mergeProfileImportReference } from "@shadowclone/profile";
import type { RepositoryIdentity } from "@shadowclone/sessions";

function opaqueHash(value: string): string {
  return new Bun.CryptoHasher("sha256").update(value).digest("hex");
}

export function repositoryAliases(options: {
  readonly workingDirectory: string;
  readonly repository: RepositoryIdentity;
}): readonly string[] {
  const aliases = [
    opaqueHash(`directory:${canonicalPath(options.workingDirectory)}`),
  ];

  if (options.repository.profileFileName !== null) {
    aliases.push(opaqueHash(`repository:${options.repository.id}`));
  }

  return aliases.sort();
}

export function sourceLocator(relativePath: string): string {
  return opaqueHash(`source:${relativePath.split("\\").join("/")}`);
}

export function matchingImportReference(options: {
  readonly stored: ProfileImportReference | null;
  readonly aliases: readonly string[];
  readonly locator: string;
}): boolean {
  return (
    options.stored !== null &&
    options.stored.sourceLocator === options.locator &&
    options.stored.repositoryAliases.some((alias) =>
      options.aliases.includes(alias),
    )
  );
}

export function mergeImportReference(options: {
  readonly stored: ProfileImportReference | null;
  readonly aliases: readonly string[];
  readonly locator: string;
}): ProfileImportReference {
  const incoming = {
    repositoryAliases: options.aliases,
    sourceLocator: options.locator,
  };

  return options.stored === null
    ? incoming
    : mergeProfileImportReference({ stored: options.stored, incoming });
}
