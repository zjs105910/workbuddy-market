import path from "node:path";
import {
  seedAgentSkillMetadataSchema,
  seedPreferenceMetadataSchema,
} from "./schema";
import type { SeedAgentSkill, SeedPreference } from "./schema";

const requiredSkillSections = [
  "## Use when",
  "## Process",
  "## Guardrails",
  "## Completion",
] as const;

function hasCompleteSkillSections(body: string): boolean {
  const lines = body.split("\n");

  return requiredSkillSections.every((section) => {
    const sectionIndexes = lines
      .map((line, lineIndex) => (line === section ? lineIndex : -1))
      .filter((lineIndex) => lineIndex >= 0);
    const [sectionIndex] = sectionIndexes;

    if (sectionIndex === undefined || sectionIndexes.length !== 1) {
      return false;
    }

    const followingLines = lines.slice(sectionIndex + 1);
    const nextSectionOffset = followingLines.findIndex((line) =>
      line.startsWith("## "),
    );
    const sectionLines =
      nextSectionOffset < 0
        ? followingLines
        : followingLines.slice(0, nextSectionOffset);

    return sectionLines.some((line) => line.trim().length > 0);
  });
}

function validateUniqueKeys(options: {
  readonly filename: string;
  readonly lines: readonly string[];
}): void {
  const seen = new Set<string>();

  for (const line of options.lines) {
    const match = line.match(/^(\s*)([a-z0-9-]+):(?:\s|$)/);

    if (!match) {
      continue;
    }

    const [, indentation, key] = match;

    if (indentation === undefined || key === undefined) {
      continue;
    }

    const identity = `${indentation.length}:${key}`;

    if (seen.has(identity)) {
      throw new Error(`Duplicate seed metadata in ${options.filename}`);
    }

    seen.add(identity);
  }
}

function parseDocument(options: {
  readonly filename: string;
  readonly text: string;
}): {
  readonly metadata: unknown;
  readonly bodyLines: readonly string[];
} {
  const lines = options.text.split(/\r?\n/);
  const [opening] = lines;
  const closingIndex = lines.indexOf("---", 1);

  if (opening !== "---" || closingIndex < 2) {
    throw new Error(`Invalid seed frontmatter in ${options.filename}`);
  }

  const metadataLines = lines.slice(1, closingIndex);

  validateUniqueKeys({ filename: options.filename, lines: metadataLines });

  try {
    return {
      metadata: Bun.YAML.parse(metadataLines.join("\n")),
      bodyLines: lines.slice(closingIndex + 1),
    };
  } catch {
    throw new Error(`Invalid seed metadata in ${options.filename}`);
  }
}

export function parseSeedPreferenceDocument(options: {
  readonly filename: string;
  readonly text: string;
}): SeedPreference {
  const document = parseDocument(options);
  const parsed = seedPreferenceMetadataSchema.safeParse(document.metadata);

  if (!parsed.success) {
    throw new Error(`Invalid preference metadata in ${options.filename}`);
  }

  if (path.basename(options.filename) !== `${parsed.data.id}.md`) {
    throw new Error(
      `Preference filename does not match its id in ${options.filename}`,
    );
  }

  const [heading, ...bodyLines] = document.bodyLines;

  if (heading !== `## ${parsed.data.title}`) {
    throw new Error(
      `Preference heading does not match its title in ${options.filename}`,
    );
  }

  const body = bodyLines.join("\n").trim();

  if (body.length === 0) {
    throw new Error(`Preference body is empty in ${options.filename}`);
  }

  return {
    kind: "preference",
    id: parsed.data.id,
    title: parsed.data.title,
    axis: parsed.data.axis,
    category: parsed.data.category,
    section: parsed.data.section,
    appliesWhen: parsed.data["applies-when"],
    body,
  };
}

export function parseSeedAgentSkillDocument(options: {
  readonly directoryName: string;
  readonly text: string;
}): SeedAgentSkill {
  const filename = `${options.directoryName}/SKILL.md`;
  const document = parseDocument({ filename, text: options.text });
  const parsed = seedAgentSkillMetadataSchema.safeParse(document.metadata);

  if (!parsed.success) {
    throw new Error(`Invalid Agent Skill metadata in ${filename}`);
  }

  if (parsed.data.name !== options.directoryName) {
    throw new Error(
      `Agent Skill directory does not match its name in ${filename}`,
    );
  }

  const [heading, ...bodyLines] = document.bodyLines;

  if (!heading?.startsWith("# ") || heading.startsWith("## ")) {
    throw new Error(`Agent Skill needs one H1 title in ${filename}`);
  }

  const title = heading.slice(2).trim();
  const body = bodyLines.join("\n").trim();

  if (title.length === 0 || !hasCompleteSkillSections(body)) {
    throw new Error(`Agent Skill workflow is incomplete in ${filename}`);
  }

  return {
    kind: "skill",
    id: parsed.data.name,
    title,
    description: parsed.data.description,
    axis: parsed.data.metadata["shadowclone-axis"] ?? null,
    category: parsed.data.metadata["shadowclone-category"],
    section: parsed.data.metadata["shadowclone-section"],
    appliesWhen: [parsed.data.metadata["shadowclone-applies-when"]],
    alwaysOn: parsed.data.metadata["shadowclone-always-on"] === "true",
    body,
  };
}
