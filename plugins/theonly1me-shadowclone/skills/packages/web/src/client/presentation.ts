import type { BrowserItem } from "../protocol";
import { skillPresentations } from "../skillPresentations";

export function skillTitle(item: BrowserItem): string {
  return skillPresentations[item.id]?.title ?? item.title;
}

export function skillSummary(options: {
  readonly item: BrowserItem;
  readonly editedText?: string;
}): string {
  const prepared = skillPresentations[options.item.id];

  if (
    prepared &&
    options.editedText === undefined &&
    options.item.owner === "packaged"
  ) {
    return prepared.summary;
  }

  const body = (options.editedText ?? options.item.text)
    .replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n/, "")
    .split("\n")
    .filter(
      (line) => line.trim() && !line.startsWith("#") && !line.startsWith("```"),
    )
    .slice(0, 2)
    .join(" ")
    .replace(/\*\*/g, "");

  return body.length > 320 ? `${body.slice(0, 317).trimEnd()}…` : body;
}

export const featuredSkills = [
  "design-deep-modules",
  "typescript-type-safety",
  "refactor-preserve",
  "diagnose-before-editing",
  "tests-that-catch-bugs",
  "verify-and-review",
  "planning-first",
  "questions-autonomous",
  "scope-confirmed-changes",
];
