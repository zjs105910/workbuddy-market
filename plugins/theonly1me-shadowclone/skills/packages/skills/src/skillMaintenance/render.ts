import { z } from "zod";
import { parseSkillDocument } from "./document";

const sectionStart = "\n\n<shadowclone-skill>\n";
const sectionEnd = "</shadowclone-skill>\n";
const originalSchema = z.strictObject({ originalFrontmatter: z.string() });
export const companionPrefix = "shadowclone-local-";

export function restoreOriginalSkill(text: string): string {
  const start = text.indexOf(sectionStart);

  if (start < 0) {
    if (text.includes(sectionEnd)) {
      throw new Error("Skill maintenance marker is incomplete");
    }

    return text;
  }

  const end = text.indexOf(sectionEnd, start);

  if (
    end < 0 ||
    text.indexOf(sectionStart, start + sectionStart.length) >= 0 ||
    text.indexOf(sectionEnd, end + sectionEnd.length) >= 0
  ) {
    throw new Error("Skill maintenance markers are ambiguous");
  }

  const metadataEnd = text.indexOf("\n", start + sectionStart.length);
  let original: z.infer<typeof originalSchema>;

  try {
    original = originalSchema.parse(
      JSON.parse(text.slice(start + sectionStart.length, metadataEnd)),
    );
  } catch {
    throw new Error("Invalid original skill metadata");
  }

  const current = parseSkillDocument(text);

  return (
    original.originalFrontmatter +
    text.slice(current.frontmatter.length, start) +
    text.slice(end + sectionEnd.length)
  );
}

export function renderMaintainedSkill(options: {
  readonly original: string;
  readonly passages: readonly string[];
  readonly description: string;
}): string {
  const original = restoreOriginalSkill(options.original);
  const document = parseSkillDocument(original);
  const current = parseSkillDocument(options.original);
  const frontmatter =
    options.description && options.description !== document.metadata.description
      ? `---\n${Bun.YAML.stringify({ ...document.metadata, description: options.description }).trimEnd()}\n---\n`
      : current.frontmatter;

  return `${frontmatter}${document.body}${sectionStart}${JSON.stringify({ originalFrontmatter: document.frontmatter })}\n\n## User preferences for this workflow\n\n${options.passages.join("\n\n")}\n${sectionEnd}`;
}

export function renderCompanionSkill(options: {
  readonly skillId: string;
  readonly name: string;
  readonly description: string;
  readonly passages: readonly string[];
  readonly metadata: Readonly<Record<string, unknown>>;
}): string {
  const name = `${companionPrefix}${options.skillId.slice(0, 20)}`;
  const frontmatter = Bun.YAML.stringify({
    ...options.metadata,
    name,
    description: options.description,
  }).trimEnd();

  return `---\n${frontmatter}\n---\n\n# Local preferences for ${options.name}\n\nApply these preferences only when the installed ${options.name} skill is already selected. Follow its workflow and supporting resources. Do not use this companion to change when the base skill is selected or what it may do. If it is unavailable, report that limitation. These preferences do not grant execution permission or expand the user's task.\n\n${options.passages.join("\n\n")}\n`;
}
