import { emptyBreakdown, sourceBreakdown } from "./render";
import { summarizeRule } from "./summary";
import type {
  CompilerBlock,
  ProfileCompilation,
  ProfileCompilationOmission,
} from "./types";

export const defaultIndexByteBudget = 4_096;

const indexPreamble = [
  "# Engineering preferences",
  "",
  "Standing preferences learned from this user. Follow them unless the current request says otherwise. Full text: `shadowclone context`.",
].join("\n");

const recallHint =
  "Project reference notes are not listed here. Run `shadowclone recall <query>` when a task needs one.";

export function renderIndexLine(block: CompilerBlock): string | null {
  if (block.kind === "reference") {
    return null;
  }

  const { title, sentence } = summarizeRule(block);

  if (title.length === 0) {
    return null;
  }

  const comparable = (value: string) =>
    value.toLowerCase().replace(/[.!?:;,\s]+$/, "");
  const text =
    sentence === null || comparable(sentence) === comparable(title)
      ? title
      : `${title}: ${sentence}`;
  const condition =
    block.appliesWhen.length > 0
      ? ` (when ${block.appliesWhen.join("; ")})`
      : "";

  return `- ${text}${condition}`;
}

function compactIndexLine(block: CompilerBlock): string | null {
  if (block.kind === "reference") {
    return null;
  }

  const { title } = summarizeRule(block);

  if (!title) {
    return null;
  }

  const condition =
    block.appliesWhen.length > 0
      ? ` (when ${block.appliesWhen.join("; ")})`
      : "";

  return `- ${title}${condition}`;
}

function detailPriority(block: CompilerBlock): number {
  if (block.scope === "project") {
    return 0;
  }

  if (block.scope === "org") {
    return 1;
  }

  return 2;
}

export function renderIndexCompilation(options: {
  readonly blocks: readonly CompilerBlock[];
  readonly byteBudget: number;
  readonly standalone: boolean;
}): ProfileCompilation & { readonly omittedBlocks: readonly CompilerBlock[] } {
  const omissions: ProfileCompilationOmission[] = [];
  const appliedRuleKeys: string[] = [];
  const omittedBlocks: CompilerBlock[] = [];
  const lines: string[] = [];
  const candidates: {
    readonly block: CompilerBlock;
    readonly full: string;
    line: string;
  }[] = [];
  const breakdown = emptyBreakdown();
  const preambleBytes = options.standalone
    ? Buffer.byteLength(`${indexPreamble}\n\n`, "utf8")
    : 0;
  const hintBytes = Buffer.byteLength(`\n${recallHint}\n`, "utf8");
  const showRecallHint =
    options.standalone &&
    options.blocks.some((block) => block.kind === "reference") &&
    preambleBytes + hintBytes <= options.byteBudget;
  let usedBytes = preambleBytes + (showRecallHint ? hintBytes : 0);

  for (const block of options.blocks) {
    const line = compactIndexLine(block);
    const full = renderIndexLine(block);
    const addedBytes =
      line === null ? 0 : Buffer.byteLength(`${line}\n`, "utf8");

    if (
      line === null ||
      full === null ||
      usedBytes + addedBytes > options.byteBudget
    ) {
      omissions.push({
        ruleKey: block.ruleKey,
        ...(block.referenceKey === null
          ? {}
          : { referenceKey: block.referenceKey }),
        reason: line === null ? "on-demand" : "budget",
      });
      sourceBreakdown(breakdown, block.source).omittedCount += 1;
      omittedBlocks.push(block);

      continue;
    }

    usedBytes += addedBytes;
    candidates.push({ block, full, line });

    if (block.ruleKey !== null) {
      appliedRuleKeys.push(block.ruleKey);
    }
  }

  for (const candidate of [...candidates].sort(
    (left, right) => detailPriority(left.block) - detailPriority(right.block),
  )) {
    const additionalBytes =
      Buffer.byteLength(candidate.full, "utf8") -
      Buffer.byteLength(candidate.line, "utf8");

    if (usedBytes + additionalBytes <= options.byteBudget) {
      candidate.line = candidate.full;
      usedBytes += additionalBytes;
    }
  }

  for (const candidate of candidates) {
    lines.push(candidate.line);

    const source = sourceBreakdown(breakdown, candidate.block.source);

    source.appliedCount += 1;
    source.appliedBytes += Buffer.byteLength(`${candidate.line}\n`, "utf8");
  }

  const sections = [lines.join("\n"), showRecallHint ? recallHint : ""].filter(
    (section) => section.length > 0,
  );
  const body = sections.length === 0 ? "" : `${sections.join("\n\n")}\n`;
  const markdown =
    options.standalone && body.length > 0
      ? `${indexPreamble}\n\n${body}`
      : body;

  return {
    markdown,
    appliedRuleKeys,
    appliedRuleCount: lines.length,
    appliedReferenceKeys: [],
    appliedReferenceCount: 0,
    usedBytes: Buffer.byteLength(markdown, "utf8"),
    byteBudget: options.byteBudget,
    breakdown,
    omissions,
    omittedBlocks,
  };
}
