import { isNotApplicable, type RepositoryApplicability } from "./applicability";
import { normalizeGuidanceText, summarizeRule } from "./summary";
import type {
  CompilerBlock,
  ProfileCompilationOmission,
  ProfileCompilationOmissionReason,
  ProfileCompilationRepositoryContext,
} from "./types";

function authorityRank(block: CompilerBlock): number {
  if (block.source === "user") {
    return 0;
  }

  if (block.source === "declared") {
    return 1;
  }

  if (block.source === "mined") {
    return 2;
  }

  if (block.source === "reference") {
    return 3;
  }

  return 4;
}

const minimumDuplicateProbeCharacters = 24;

function isKnownNativeDuplicate(options: {
  readonly block: CompilerBlock;
  readonly knownNativeText: readonly string[];
}): boolean {
  if (options.block.kind !== "rule" || options.knownNativeText.length === 0) {
    return false;
  }

  const summary = summarizeRule(options.block);
  const probe = normalizeGuidanceText(summary.sentence ?? summary.title);

  return (
    probe.length >= minimumDuplicateProbeCharacters &&
    options.knownNativeText.some((text) => text.includes(probe))
  );
}

function selectionOmission(options: {
  readonly block: CompilerBlock;
  readonly repositoryContext: ProfileCompilationRepositoryContext;
  readonly knownNativeText: readonly string[];
  readonly applicability?: RepositoryApplicability;
  readonly committedRuleKeys?: ReadonlySet<string>;
}): ProfileCompilationOmissionReason | null {
  const { block } = options;

  if (block.source === "imported" && options.repositoryContext === "native") {
    return "native-duplicate";
  }

  if (block.status !== "active") {
    return block.status;
  }

  if (block.ruleKey !== null && options.committedRuleKeys?.has(block.ruleKey)) {
    return "in-harness";
  }

  if (
    isKnownNativeDuplicate({ block, knownNativeText: options.knownNativeText })
  ) {
    return "known-duplicate";
  }

  if (
    options.applicability &&
    isNotApplicable({ block, applicability: options.applicability })
  ) {
    return "not-applicable";
  }

  return null;
}

function compareBlocks(left: CompilerBlock, right: CompilerBlock): number {
  return (
    authorityRank(left) - authorityRank(right) ||
    right.observations - left.observations ||
    (left.ruleKey ?? left.referenceKey ?? "").localeCompare(
      right.ruleKey ?? right.referenceKey ?? "",
    ) ||
    left.visible.localeCompare(right.visible)
  );
}

export function selectCompilerBlocks(options: {
  readonly blocks: readonly CompilerBlock[];
  readonly axes: ReadonlyMap<string, string>;
  readonly repositoryContext: ProfileCompilationRepositoryContext;
  readonly knownNativeText?: readonly string[];
  readonly applicability?: RepositoryApplicability;
  readonly committedRuleKeys?: ReadonlySet<string>;
}): {
  readonly selected: readonly CompilerBlock[];
  readonly omissions: readonly ProfileCompilationOmission[];
  readonly omittedBlocks: readonly CompilerBlock[];
} {
  const omissions: ProfileCompilationOmission[] = [];
  const omittedBlocks: CompilerBlock[] = [];
  const eligible: CompilerBlock[] = [];
  const knownNativeText = (options.knownNativeText ?? []).map(
    normalizeGuidanceText,
  );

  for (const block of options.blocks) {
    const reason = selectionOmission({
      block,
      repositoryContext: options.repositoryContext,
      knownNativeText,
      applicability: options.applicability,
      committedRuleKeys: options.committedRuleKeys,
    });

    if (reason === null) {
      eligible.push(block);

      continue;
    }

    omissions.push({ ruleKey: block.ruleKey, reason });
    omittedBlocks.push(block);
  }

  const claimedAxes = new Set<string>();
  const selected: CompilerBlock[] = [];

  for (const block of [...eligible].sort(compareBlocks)) {
    const axis =
      block.ruleKey === null ? undefined : options.axes.get(block.ruleKey);

    if (axis === undefined) {
      selected.push(block);

      continue;
    }

    if (claimedAxes.has(axis)) {
      omissions.push({ ruleKey: block.ruleKey, reason: "axis-conflict" });
      omittedBlocks.push(block);

      continue;
    }

    claimedAxes.add(axis);
    selected.push(block);
  }

  return { selected, omissions, omittedBlocks };
}
