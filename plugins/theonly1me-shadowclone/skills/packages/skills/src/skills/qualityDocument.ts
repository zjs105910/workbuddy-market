import { seedAgentSkillMetadataSchema } from "./schema";

export type BodyLine = {
  readonly number: number;
  readonly text: string;
};

export type SkillSection = {
  readonly heading: string;
  readonly line: number;
  readonly lines: readonly BodyLine[];
};

export type SkillDocument = {
  readonly name: string;
  readonly description: string;
  readonly descriptionLine: number;
  readonly appliesWhen: string;
  readonly appliesWhenLine: number;
  readonly voice: boolean;
  readonly voiceLine: number;
  readonly bodyStartLine: number;
  readonly bodyLines: readonly BodyLine[];
  readonly sections: readonly SkillSection[];
};

function lineOfKey(options: { readonly lines: readonly string[]; readonly key: string }): number {
  const index = options.lines.findIndex((line) => line.trimStart().startsWith(`${options.key}:`));

  return index < 0 ? 1 : index + 1;
}

function trimTrailingBlankLines(lines: readonly BodyLine[]): readonly BodyLine[] {
  const lastFilled = lines.findLastIndex((line) => line.text.trim().length > 0);

  return lines.slice(0, lastFilled + 1);
}

function readSections(lines: readonly BodyLine[]): readonly SkillSection[] {
  const sections: SkillSection[] = [];

  for (const [position, line] of lines.entries()) {
    if (!line.text.startsWith("## ")) {
      continue;
    }

    const following = lines.slice(position + 1);
    const nextHeading = following.findIndex((candidate) => candidate.text.startsWith("## "));

    sections.push({
      heading: line.text,
      line: line.number,
      lines: nextHeading < 0 ? following : following.slice(0, nextHeading),
    });
  }

  return sections;
}

export function readSkillDocument(text: string): SkillDocument | null {
  const lines = text.split(/\r?\n/);
  const closingIndex = lines.indexOf("---", 1);

  if (lines[0] !== "---" || closingIndex < 2) {
    return null;
  }

  const frontmatter = lines.slice(1, closingIndex);
  let metadata: unknown;

  try {
    metadata = Bun.YAML.parse(frontmatter.join("\n"));
  } catch {
    return null;
  }

  const parsed = seedAgentSkillMetadataSchema.safeParse(metadata);

  if (!parsed.success) {
    return null;
  }

  const bodyLines = trimTrailingBlankLines(
    lines
      .slice(closingIndex + 1)
      .map((line, offset) => ({ number: closingIndex + 2 + offset, text: line })),
  );
  const [firstBodyLine] = bodyLines;

  return {
    name: parsed.data.name,
    description: parsed.data.description,
    descriptionLine: 1 + lineOfKey({ lines: frontmatter, key: "description" }),
    appliesWhen: parsed.data.metadata["shadowclone-applies-when"],
    appliesWhenLine: 1 + lineOfKey({ lines: frontmatter, key: "shadowclone-applies-when" }),
    voice: parsed.data.metadata["shadowclone-voice"] === "true",
    voiceLine: 1 + lineOfKey({ lines: frontmatter, key: "shadowclone-voice" }),
    bodyStartLine: firstBodyLine?.number ?? closingIndex + 2,
    bodyLines,
    sections: readSections(bodyLines),
  };
}
