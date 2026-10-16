const attributionLine = /^\s*(?:🤖\s*)?(?:generated (?:with|by)\b|co-authored-by:)/iu;

export function withoutAttribution(text: string): string {
  return text.split("\n").filter((line) => !attributionLine.test(line)).join("\n").trim();
}
