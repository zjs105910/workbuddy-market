export function normalizeCode(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

const singleQuotes = new RegExp(`[${String.fromCodePoint(0x2018, 0x2019)}]`, "g");
const doubleQuotes = new RegExp(`[${String.fromCodePoint(0x201c, 0x201d)}]`, "g");
const dashes = new RegExp(`[${String.fromCodePoint(0x2013, 0x2014)}]`, "g");

export function normalizeProse(text: string): string {
  return text
    .replace(singleQuotes, "'")
    .replace(doubleQuotes, '"')
    .replace(dashes, "-")
    .replace(/`/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

export function diffContent(diffText: string): string {
  return diffText
    .split("\n")
    .filter((line) => !/^(?:diff --git |index |--- |\+\+\+ |@@ )/.test(line))
    .map((line) => line.slice(1))
    .join("\n");
}

export type CodeLocation = { readonly path: string; readonly start: number; readonly end: number };

export function parseCodeLocation(location: string): CodeLocation | null {
  const groups = /^(?<path>[^:\s]+):(?<start>\d+)(?:-(?<end>\d+))?$/.exec(location.trim())?.groups;

  if (!groups?.path || !groups.start) {
    return null;
  }

  const start = Number(groups.start);

  return { path: groups.path, start, end: groups.end ? Math.max(start, Number(groups.end)) : start };
}
