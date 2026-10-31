import type { LineRange } from "../types";

export type AddedLine = {
  readonly line: number;
  readonly text: string;
};

export type DiffFile = {
  readonly path: string;
  readonly deleted: boolean;
  readonly text: string;
  readonly changedLines: number;
  readonly ranges: readonly LineRange[];
  readonly added: readonly AddedLine[];
};

const hunkHeader = /^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@/;

function unquote(value: string): string {
  const trimmed = value.replace(/\t$/, "");

  if (!trimmed.startsWith('"') || !trimmed.endsWith('"')) {
    return trimmed;
  }

  return trimmed.slice(1, -1).replaceAll('\\"', '"').replaceAll("\\\\", "\\");
}

function sidePath(options: {
  readonly headerLines: readonly string[];
  readonly marker: string;
  readonly prefix: string;
}): string | null {
  const line = options.headerLines.find((candidate) => candidate.startsWith(options.marker));

  if (!line) {
    return null;
  }

  const value = unquote(line.slice(options.marker.length));

  return value.startsWith(options.prefix) ? value.slice(options.prefix.length) : null;
}

function headerPath(header: string): string {
  const match = /^diff --git (?:"?a\/.*"?) "?b\/(.*?)"?$/.exec(header);

  return match?.[1] ?? header.slice("diff --git ".length);
}

function parseSection(section: string): DiffFile {
  const lines = section.split("\n");
  const firstHunk = lines.findIndex((line) => hunkHeader.test(line));
  const headerLines = firstHunk < 0 ? lines : lines.slice(0, firstHunk);
  const [header = ""] = headerLines;
  const deleted = headerLines.includes("+++ /dev/null");
  const ranges: LineRange[] = [];
  const added: AddedLine[] = [];
  let changedLines = 0;
  let nextLine = 0;

  for (const line of firstHunk < 0 ? [] : lines.slice(firstHunk)) {
    const hunk = hunkHeader.exec(line);

    if (hunk) {
      const start = Number(hunk[1]);
      const count = hunk[2] === undefined ? 1 : Number(hunk[2]);

      if (count > 0) {
        ranges.push([start, start + count - 1]);
      }

      nextLine = start;
      continue;
    }

    if (line.startsWith("+")) {
      added.push({ line: nextLine, text: line.slice(1) });
      changedLines += 1;
      nextLine += 1;
    } else if (line.startsWith("-")) {
      changedLines += 1;
    } else if (line.startsWith(" ")) {
      nextLine += 1;
    }
  }

  const newPath = sidePath({ headerLines, marker: "+++ ", prefix: "b/" });
  const oldPath = sidePath({ headerLines, marker: "--- ", prefix: "a/" });

  return {
    path: (deleted ? oldPath : newPath) ?? headerPath(header),
    deleted,
    text: section,
    changedLines,
    ranges,
    added,
  };
}

export function parseDiff(text: string): readonly DiffFile[] {
  return text
    .split(/^(?=diff --git )/m)
    .filter((section) => section.startsWith("diff --git "))
    .map(parseSection);
}
