import type { SkillDocument } from "./qualityDocument";
import { finding, type SkillFinding } from "./qualityTypes";

const reservedNames = new Set([
  "planning",
  "plan",
  "scoped-fix",
  "clean-code",
  "creating-prs",
  "triage-review-findings",
  "split-to-prs",
  "autopilot",
  "tdd",
  "testing",
  "review",
  "debugging",
]);

export function descriptionFindings(options: {
  readonly document: SkillDocument;
  readonly bundledNames: readonly string[];
}): readonly SkillFinding[] {
  const { document } = options;
  const at = { skill: document.name, line: document.descriptionLine, rule: "description" } as const;
  const findings: SkillFinding[] = [];
  const length = document.description.length;
  const quotedPhrases = document.description.match(/"[^"]+"/g) ?? [];
  const notFor = /Not for [^()]+\(use `?([a-z0-9-]+)`?\)\.?$/.exec(document.description.trim());
  const alternative = notFor?.[1];

  if (length < 250 || length > 900) {
    findings.push(finding({ ...at, message: `${length} characters, keep it between 250 and 900` }));
  }

  if (!/^Use (?:when|before)\b/.test(document.description)) {
    findings.push(finding({ ...at, message: 'start with "Use when" or "Use before"' }));
  }

  if (quotedPhrases.length < 2) {
    findings.push(finding({ ...at, message: "quote at least two phrases a user says" }));
  }

  if (alternative === undefined) {
    findings.push(finding({ ...at, message: 'end with "Not for ... (use `<skill>`)."' }));
  } else if (alternative === document.name || !options.bundledNames.includes(alternative)) {
    findings.push(
      finding({
        ...at,
        message: `"Not for" names ${alternative}, which is not another bundled skill`,
      }),
    );
  }

  return findings;
}

export function nameFindings(document: SkillDocument): readonly SkillFinding[] {
  return document.name.includes("-") && !reservedNames.has(document.name)
    ? []
    : [
        finding({
          skill: document.name,
          line: 2,
          rule: "name",
          message: "use at least two words that no personal skill commonly uses",
        }),
      ];
}

export function appliesWhenFindings(document: SkillDocument): readonly SkillFinding[] {
  return document.appliesWhen.length <= 90 &&
    /^(?:before|when|after|while)\b/.test(document.appliesWhen)
    ? []
    : [
        finding({
          skill: document.name,
          line: document.appliesWhenLine,
          rule: "applies-when",
          message:
            "write a moment of at most 90 characters that starts with before, when, after, or while",
        }),
      ];
}
