import { parseSkillDocument } from "@shadowclone/skills";
import { z } from "zod";

type SkillClassification = {
  readonly appliesWhen: string | null;
  readonly axis: string | null;
  readonly category: string | null;
  readonly section: string | null;
};

function metadataText(
  metadata: Record<string, unknown>,
  key: string,
): string | null {
  const value = metadata[key];

  return typeof value === "string" && value.trim() ? value.trim() : null;
}

export function skillClassification(text: string): SkillClassification {
  const { metadata } = parseSkillDocument(text);
  const nested = z
    .record(z.string(), z.unknown())
    .safeParse(metadata.metadata);
  const classification = nested.success ? nested.data : metadata;

  return {
    appliesWhen: metadataText(classification, "shadowclone-applies-when"),
    axis: metadataText(classification, "shadowclone-axis"),
    category: metadataText(classification, "shadowclone-category"),
    section: metadataText(classification, "shadowclone-section"),
  };
}
