import { parseProfileBlocks } from "../parse";
import { locatedRule } from "../located";
import { renderProfileRule } from "../render";
import { parseReference, renderReference } from "../../references";
import { repairRuleEvidence } from "./evidence";

export type MergeResult =
  | { readonly content: string }
  | {
      readonly blocked: "conflicting-rule" | "edited-block" | "invalid-content";
    };

function repairedBlocks(options: {
  readonly content: string;
  readonly targetRelativePath: string;
  readonly originId: string;
}): readonly { readonly key: string; readonly content: string }[] | null {
  const blocks = parseProfileBlocks(options.content);

  if (blocks.some((block) => block.key === null || block.edited)) {
    return null;
  }

  return blocks.flatMap((block) => {
    if (block.key === null) {
      return [];
    }

    const located = locatedRule({
      existing: block,
      relativePath: options.targetRelativePath,
    });

    if (located === null) {
      return [];
    }

    const rule = repairRuleEvidence({
      rule: located,
      originId: options.originId,
    });

    return [{ key: rule.key, content: renderProfileRule(rule) }];
  });
}

export function mergeProfileContent(options: {
  readonly source: string;
  readonly target: string | null;
  readonly targetRelativePath: string;
  readonly originId: string;
}): MergeResult {
  const source = repairedBlocks({
    content: options.source,
    targetRelativePath: options.targetRelativePath,
    originId: options.originId,
  });

  if (source === null) {
    return { blocked: "edited-block" };
  }

  const target =
    options.target === null
      ? []
      : repairedBlocks({
          content: options.target,
          targetRelativePath: options.targetRelativePath,
          originId: options.originId,
        });

  if (target === null) {
    return { blocked: "edited-block" };
  }

  const merged = new Map(target.map((block) => [block.key, block.content]));

  for (const block of source) {
    const current = merged.get(block.key);

    if (current !== undefined && current !== block.content) {
      return { blocked: "conflicting-rule" };
    }

    merged.set(block.key, block.content);
  }

  return { content: `${[...merged.values()].join("\n\n")}\n` };
}

export function mergeReferenceContent(options: {
  readonly source: string;
  readonly target: string | null;
  readonly targetDirectory: string;
}): MergeResult {
  const source = parseReference(options.source);

  if (source === null || source.scope === "global") {
    return { blocked: "invalid-content" };
  }

  const repaired = renderReference({
    ...source,
    originDirectory: options.targetDirectory,
  });

  if (options.target === null) {
    return { content: repaired };
  }

  const target = parseReference(options.target);

  if (target === null) {
    return { blocked: "invalid-content" };
  }

  return renderReference(target) === repaired
    ? { content: repaired }
    : { blocked: "conflicting-rule" };
}
