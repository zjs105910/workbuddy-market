import type { SkillDocument, SkillSection } from "./qualityDocument";
import { finding, type SkillFinding, type SkillRule } from "./qualityTypes";

const sectionRules = [
  { heading: "## Use when", rule: null },
  { heading: "## Gates", rule: "gates" },
  { heading: "## Process", rule: null },
  { heading: "## Example", rule: "example" },
  { heading: "## Guardrails", rule: null },
  { heading: "## Completion", rule: null },
] as const;

const exampleLabels = ["Situation", "Easy route", "Hidden cost", "Best route", "Evidence"] as const;

const maximumBodyLines = 150;
const gatesWithinLines = 40;

export function sectionFindings(options: {
  readonly document: SkillDocument;
  readonly exemptions: readonly SkillRule[];
}): readonly SkillFinding[] {
  const expected = sectionRules
    .filter((section) => section.rule === null || !options.exemptions.includes(section.rule))
    .map((section) => section.heading);
  const actual = options.document.sections.map((section) => section.heading);

  if (expected.join("\n") === actual.join("\n")) {
    return [];
  }

  return [
    finding({
      skill: options.document.name,
      line: options.document.bodyStartLine,
      rule: "sections",
      message: `use the sections ${expected.map((heading) => heading.slice(3)).join(", ")} in that order`,
    }),
  ];
}

function sectionNamed(options: {
  readonly document: SkillDocument;
  readonly heading: string;
}): SkillSection | undefined {
  return options.document.sections.find((section) => section.heading === options.heading);
}

function filledLines(section: SkillSection) {
  return section.lines.filter((line) => line.text.trim().length > 0);
}

export function gateFindings(document: SkillDocument): readonly SkillFinding[] {
  const gates = sectionNamed({ document, heading: "## Gates" });

  if (gates === undefined) {
    return [];
  }

  const at = { skill: document.name, line: gates.line, rule: "gates" } as const;
  const items = gates.lines.filter((line) => /^\d+\. \S/.test(line.text));
  const lastLine = filledLines(gates).at(-1)?.number ?? gates.line;
  const findings: SkillFinding[] = [];

  if (items.length < 3 || items.length > 6) {
    findings.push(finding({ ...at, message: `${items.length} numbered gates, use 3 to 6` }));
  }

  if (lastLine - document.bodyStartLine + 1 > gatesWithinLines) {
    findings.push(
      finding({
        ...at,
        message: `gates end on body line ${lastLine - document.bodyStartLine + 1}, keep them in the first ${gatesWithinLines}`,
      }),
    );
  }

  return findings;
}

export function exampleFindings(document: SkillDocument): readonly SkillFinding[] {
  const example = sectionNamed({ document, heading: "## Example" });

  if (example === undefined) {
    return [];
  }

  const missing = exampleLabels.filter(
    (label) =>
      !example.lines.some((line) => new RegExp(`^(?:- )?\\*\\*${label}:\\*\\*`).test(line.text)),
  );

  return missing.length === 0
    ? []
    : [
        finding({
          skill: document.name,
          line: example.line,
          rule: "example",
          message: `add ${missing.map((label) => `**${label}:**`).join(", ")}`,
        }),
      ];
}

export function completionFindings(document: SkillDocument): readonly SkillFinding[] {
  const completion = sectionNamed({ document, heading: "## Completion" });

  if (completion === undefined) {
    return [];
  }

  const items = completion.lines.filter((line) => /^(?:- |\d+\. )\S/.test(line.text));

  return items.length >= 1 && items.length <= 6
    ? []
    : [
        finding({
          skill: document.name,
          line: completion.line,
          rule: "completion",
          message: `${items.length} report items, list 1 to 6`,
        }),
      ];
}

export function bodyLengthFindings(document: SkillDocument): readonly SkillFinding[] {
  return document.bodyLines.length <= maximumBodyLines
    ? []
    : [
        finding({
          skill: document.name,
          line: document.bodyStartLine,
          rule: "body-length",
          message: `${document.bodyLines.length} body lines, keep at most ${maximumBodyLines}`,
        }),
      ];
}
