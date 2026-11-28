import type {
  CompilerBlock,
  ProfileCompilation,
  ProfileCompilationBreakdown,
  ProfileCompilationOmission,
  ProfileCompilationSource,
} from "./types";

export const defaultProfileByteBudget = 16_384;

const profilePreamble = "# Shadowclone profile";

const sourceLabels = {
  user: "written by the user",
  declared: "declared by the user",
  imported: "imported from repository guidance",
  mined: "observed in the user's sessions",
} as const;

const compilationSources: readonly ProfileCompilationSource[] = [
  "user",
  "declared",
  "mined",
  "reference",
  "imported",
];

function renderBlock(block: CompilerBlock): string {
  if (block.kind === "reference") {
    return block.visible;
  }

  const lines = [
    block.visible,
    "",
    `Guidance source: ${sourceLabels[block.source]}`,
  ];

  if (block.appliesWhen.length > 0) {
    lines.push(`Applies when: ${block.appliesWhen.join(", ")}`);
  }

  return lines.join("\n");
}

export type MutableBreakdown = {
  source: ProfileCompilationSource;
  appliedCount: number;
  omittedCount: number;
  appliedBytes: number;
};

export function emptyBreakdown(): MutableBreakdown[] {
  return compilationSources.map((source) => ({
    source,
    appliedCount: 0,
    omittedCount: 0,
    appliedBytes: 0,
  }));
}

export function sourceBreakdown(
  breakdown: MutableBreakdown[],
  source: ProfileCompilationSource,
): MutableBreakdown {
  const entry = breakdown.find((value) => value.source === source);

  if (entry === undefined) {
    throw new Error("Unknown compilation source");
  }

  return entry;
}

export function renderCompilation(options: {
  readonly blocks: readonly CompilerBlock[];
  readonly byteBudget: number;
}): ProfileCompilation & { readonly omittedBlocks: readonly CompilerBlock[] } {
  const omissions: ProfileCompilationOmission[] = [];
  const appliedRuleKeys: string[] = [];
  const appliedReferenceKeys: string[] = [];
  const omittedBlocks: CompilerBlock[] = [];
  const rendered: string[] = [];
  const breakdown = emptyBreakdown();
  let appliedRuleCount = 0;
  let usedBytes = Buffer.byteLength(`${profilePreamble}\n`, "utf8");

  for (const block of options.blocks) {
    const text = renderBlock(block);
    const addedBytes = Buffer.byteLength(`\n${text}\n`, "utf8");

    if (usedBytes + addedBytes > options.byteBudget) {
      omissions.push({
        ruleKey: block.ruleKey,
        ...(block.referenceKey === null
          ? {}
          : { referenceKey: block.referenceKey }),
        reason: "budget",
      });
      sourceBreakdown(breakdown, block.source).omittedCount += 1;
      omittedBlocks.push(block);

      continue;
    }

    usedBytes += addedBytes;
    rendered.push(text);

    const source = sourceBreakdown(breakdown, block.source);

    source.appliedCount += 1;
    source.appliedBytes += addedBytes;

    if (block.ruleKey !== null) {
      appliedRuleKeys.push(block.ruleKey);
    }

    if (block.kind === "rule") {
      appliedRuleCount += 1;
    }

    if (block.referenceKey !== null) {
      appliedReferenceKeys.push(block.referenceKey);
    }
  }

  return {
    markdown:
      rendered.length === 0
        ? `${profilePreamble}\n`
        : `${profilePreamble}\n\n${rendered.join("\n\n")}\n`,
    appliedRuleKeys,
    appliedRuleCount,
    appliedReferenceKeys,
    appliedReferenceCount: appliedReferenceKeys.length,
    usedBytes,
    byteBudget: options.byteBudget,
    breakdown,
    omissions,
    omittedBlocks,
  };
}

export function addOmittedBreakdown(options: {
  readonly breakdown: readonly ProfileCompilationBreakdown[];
  readonly blocks: readonly CompilerBlock[];
}): readonly ProfileCompilationBreakdown[] {
  return options.breakdown.map((entry) => ({
    ...entry,
    omittedCount:
      entry.omittedCount +
      options.blocks.filter((block) => block.source === entry.source).length,
  }));
}
