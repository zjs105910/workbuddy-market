import { markdownLines } from "./markdownLines";

const headingPattern = /^ {0,3}#{1,6}\s+(.*?)(?:\s+#+)?\s*$/;

function headingText(raw: string): string {
  return raw
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/[`*]/g, "");
}

function slugOf(heading: string): string {
  return headingText(heading)
    .toLowerCase()
    .replace(/[^\p{L}\p{N}_\- ]/gu, "")
    .replace(/ /g, "-");
}

export function headingSlugs(text: string): ReadonlySet<string> {
  const slugs = new Set<string>();
  const seen = new Map<string, number>();

  for (const line of markdownLines(text)) {
    const heading = line.inFence ? null : headingPattern.exec(line.text)?.[1];

    if (heading === undefined || heading === null) {
      continue;
    }

    const base = slugOf(heading);
    const count = seen.get(base) ?? 0;

    slugs.add(count === 0 ? base : `${base}-${count}`);
    seen.set(base, count + 1);
  }

  return slugs;
}
