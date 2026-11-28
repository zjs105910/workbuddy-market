import type { ProfileFile } from "./files";
import { generatedProfileEntry, type PreparedProfileWrite } from "./lifecycle";
import { migratedLegacyRule } from "./migrate";
import { metadataReplacement } from "./metadataReplacement";
import { profileRulePath, renderProfileRule } from "./render";
import type { GeneratedProfileStateEntry } from "./state";

export function renderProfileBlocks(options: {
  readonly file: ProfileFile;
  readonly prepared: PreparedProfileWrite;
  readonly consumed: Set<string>;
  readonly nextState: Map<string, GeneratedProfileStateEntry>;
}): readonly string[] {
  const { file, prepared, consumed, nextState } = options;

  const nextBlocks: string[] = [];

  for (const block of file.blocks) {
    if (block.key === null) {
      nextBlocks.push(block.content);

      continue;
    }

    const metadataUpdate = metadataReplacement({
      block,
      incoming: prepared.incoming.get(block.key),
      relativePath: file.relativePath,
    });

    if (metadataUpdate) {
      nextBlocks.push(renderProfileRule(metadataUpdate));
      consumed.add(block.key);

      if (metadataUpdate.importReference !== null) {
        nextState.set(
          block.key,
          generatedProfileEntry({
            relativePath: file.relativePath,
            rule: metadataUpdate,
          }),
        );
      }

      continue;
    }

    if (block.edited || block.source === "user") {
      nextBlocks.push(block.content);

      if (block.importReference !== null) {
        nextState.set(
          block.key,
          generatedProfileEntry({
            relativePath: file.relativePath,
            rule: block,
          }),
        );
      }

      continue;
    }

    if (prepared.retired.has(block.key)) {
      continue;
    }

    const replacement = prepared.incoming.get(block.key);

    if (replacement) {
      if (profileRulePath(replacement) !== file.relativePath) {
        continue;
      }

      nextBlocks.push(renderProfileRule(replacement));
      consumed.add(block.key);

      if (replacement.source !== "user") {
        nextState.set(
          block.key,
          generatedProfileEntry({
            relativePath: file.relativePath,
            rule: replacement,
          }),
        );
      }

      continue;
    }

    const migrated = migratedLegacyRule({
      block,
      relativePath: file.relativePath,
    });
    const carried = migrated ?? block;

    nextBlocks.push(migrated ? renderProfileRule(migrated) : block.content);
    consumed.add(block.key);
    nextState.set(
      block.key,
      generatedProfileEntry({
        relativePath: file.relativePath,
        rule: carried,
      }),
    );
  }

  for (const rule of prepared.incomingRules) {
    if (
      profileRulePath(rule) !== file.relativePath ||
      consumed.has(rule.key) ||
      prepared.pinned.has(rule.key) ||
      prepared.retired.has(rule.key) ||
      prepared.rejections.has(rule.key)
    ) {
      continue;
    }

    nextBlocks.push(renderProfileRule(rule));
    consumed.add(rule.key);

    if (rule.source !== "user") {
      nextState.set(
        rule.key,
        generatedProfileEntry({
          relativePath: file.relativePath,
          rule,
        }),
      );
    }
  }

  return nextBlocks;
}
