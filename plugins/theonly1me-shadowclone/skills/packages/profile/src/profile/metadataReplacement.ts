import { profileRulePath } from "./render";
import type { ExistingProfileRule, ProfileRule } from "./types";

export function metadataReplacement(options: {
  readonly block: ExistingProfileRule;
  readonly incoming: ProfileRule | undefined;
  readonly relativePath: string;
}): ProfileRule | null {
  const incoming = options.incoming;

  if (
    incoming?.source !== "user" ||
    incoming.title !== options.block.title ||
    incoming.body !== options.block.body ||
    profileRulePath(incoming) !== options.relativePath
  ) {
    return null;
  }

  return incoming;
}
