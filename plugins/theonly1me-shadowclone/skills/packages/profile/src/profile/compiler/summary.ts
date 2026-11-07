import type { CompilerBlock } from "./types";

const maximumSummaryCharacters = 240;

export type RuleSummary = {
  readonly title: string;
  readonly sentence: string | null;
};

function firstSentence(body: string): string | null {
  const [paragraph = ""] = body.split(/\n\s*\n/);
  const flattened = paragraph.replaceAll(/\s+/g, " ").trim();

  if (
    flattened.length === 0 ||
    flattened.includes("```") ||
    /^[#|>]/.test(flattened)
  ) {
    return null;
  }

  const sentence = flattened.match(/^(.+?[.!?])(?:\s|$)/)?.[1] ?? flattened;

  return sentence.length > maximumSummaryCharacters ? null : sentence;
}

export function summarizeRule(block: CompilerBlock): RuleSummary {
  const [heading = "", ...rest] = block.visible.trim().split("\n");
  const title = heading.replace(/^#+\s*/, "").trim();

  return { title, sentence: firstSentence(rest.join("\n").trim()) };
}

export function normalizeGuidanceText(text: string): string {
  return text
    .toLowerCase()
    .replaceAll(/[`*_]/g, "")
    .replaceAll(/\s+/g, " ")
    .trim();
}
