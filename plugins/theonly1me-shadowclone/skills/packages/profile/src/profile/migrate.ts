import { activatesFromSessions } from "./evidence";
import { locatedRule } from "./located";
import type { ExistingProfileBlock, ProfileRule } from "./types";

export function isMigratableLegacyBlock(
  block: ExistingProfileBlock,
): block is Extract<ExistingProfileBlock, { readonly key: string }> {
  return block.key !== null && block.legacy && !block.edited;
}

export function migratedLegacyRule(options: {
  readonly block: ExistingProfileBlock;
  readonly relativePath: string;
}): ProfileRule | null {
  if (!isMigratableLegacyBlock(options.block)) {
    return null;
  }

  const located = locatedRule({
    existing: options.block,
    relativePath: options.relativePath,
  });

  if (located === null) {
    return null;
  }

  return {
    ...located,
    source: "mined",
    status: activatesFromSessions(options.block.sessions)
      ? "active"
      : "candidate",
    proposal: null,
    appliesWhen: [],
    evidence: { for: [], against: [] },
    importReference: null,
  };
}
