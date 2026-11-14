import type { RepositoryGuidanceSource } from "./discovery";
import { stripHarnessSection, stripManagedGuidance } from "@shadowclone/environment";

export type ImportedGuidanceContent = {
  readonly title: string;
  readonly body: string;
};

type Fence = {
  readonly marker: "`" | "~";
  readonly length: number;
};

const rootTitles: Readonly<Record<string, string>> = {
  "AGENTS.md": "Repository instructions from AGENTS.md",
  "CLAUDE.md": "Repository instructions from CLAUDE.md",
  ".cursorrules": "Repository instructions from .cursorrules",
};

function withoutLeadingFrontmatter(text: string): string {
  const lines = text.split("\n");

  if (lines[0]?.trim() !== "---") {
    return text;
  }

  const end = lines.findIndex(
    (line, index) => index > 0 && line.trim() === "---",
  );

  return end === -1
    ? text
    : lines
        .slice(end + 1)
        .join("\n")
        .trimStart();
}

function openingFence(line: string): Fence | null {
  const match = line.match(/^ {0,3}(`{3,}|~{3,})/);
  const marker = match?.[1];

  if (!marker) {
    return null;
  }

  return {
    marker: marker[0] === "`" ? "`" : "~",
    length: marker.length,
  };
}

function closesFence(line: string, fence: Fence): boolean {
  const trimmed = line.trimStart();
  const marker = fence.marker.repeat(fence.length);

  return (
    trimmed.startsWith(marker) &&
    trimmed.slice(fence.length).trim().replaceAll(fence.marker, "").length === 0
  );
}

function firstHeading(text: string): string | null {
  let fence: Fence | null = null;

  for (const line of text.split("\n")) {
    if (fence !== null) {
      if (closesFence(line, fence)) {
        fence = null;
      }

      continue;
    }

    fence = openingFence(line);

    if (fence !== null) {
      continue;
    }

    const match = line.match(/^ {0,3}#\s+(.+?)\s*#*\s*$/);

    if (match?.[1]) {
      return match[1].trim();
    }
  }

  return null;
}

export function nestMarkdownHeadings(text: string): string {
  let fence: Fence | null = null;
  const lines: string[] = [];

  for (const line of text.split("\n")) {
    if (fence !== null) {
      if (closesFence(line, fence)) {
        fence = null;
      }

      lines.push(line);

      continue;
    }

    fence = openingFence(line);

    if (fence !== null) {
      lines.push(line);

      continue;
    }

    lines.push(
      line.replace(
        /^( {0,3})(#{1,6})(\s+)/,
        (_match, indentation: string, hashes: string, spacing: string) =>
          `${indentation}${"#".repeat(Math.min(6, hashes.length + 2))}${spacing}`,
      ),
    );
  }

  const nested = lines.join("\n").trim();

  return fence === null
    ? nested
    : `${nested}\n${fence.marker.repeat(fence.length)}`;
}

export function transformRepositoryGuidance(options: {
  readonly source: RepositoryGuidanceSource;
  readonly redactedText: string;
}): ImportedGuidanceContent | null {
  const normalized = stripHarnessSection(
    stripManagedGuidance(options.redactedText.replaceAll("\r\n", "\n")),
  );
  const withoutFrontmatter =
    options.source.kind === "skill"
      ? withoutLeadingFrontmatter(normalized)
      : normalized;
  const body = nestMarkdownHeadings(withoutFrontmatter);

  if (body.length === 0) {
    return null;
  }

  const title =
    options.source.kind === "skill"
      ? `Repository skill: ${firstHeading(withoutFrontmatter) ?? "Imported guidance"}`
      : (rootTitles[options.source.relativePath] ?? "Repository instructions");

  return { title, body };
}
