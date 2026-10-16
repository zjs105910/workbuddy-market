const toolNames = /\b(shadowclone|openqodex|greptile|greptileai|claude|codex)\b/gi;

export type NormalizedFinding = {
  readonly arm: string;
  readonly caseId: string;
  readonly path: string;
  readonly line: number | null;
  readonly text: string;
};

export function plainText(markdown: string): string {
  return markdown
    .replace(/<!--[\s\S]*?-->/g, " ")
    .replace(/<details>[\s\S]*?<\/details>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/!\[[^\]]*\]\([^)]*\)/g, " ")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/https?:\/\/\S+/g, " ")
    .replace(/[*_#>]+/g, "")
    .replace(toolNames, "the reviewer")
    .replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/gu, "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 1_500);
}
