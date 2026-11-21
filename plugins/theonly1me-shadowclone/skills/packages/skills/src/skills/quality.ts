import { readSkillDocument } from "./qualityDocument";
import { appliesWhenFindings, descriptionFindings, nameFindings } from "./qualityFrontmatter";
import {
  bodyLengthFindings,
  completionFindings,
  exampleFindings,
  gateFindings,
  sectionFindings,
} from "./qualitySections";
import { finding, type SkillFinding, type SkillRule } from "./qualityTypes";
import type { SkillDocument } from "./qualityDocument";
import { voiceBlock } from "./voiceBlock";

export type { SkillFinding, SkillRule } from "./qualityTypes";

const hostOnlyTools =
  /\b(?:AskUserQuestion|TodoWrite|ExitPlanMode|EnterPlanMode|request_user_input|SendMessage|WebFetch|WebSearch|Skill tool|Task tool)\b/;

const supportingReference =
  /`((?:scripts|references|assets)\/[^`\s]+)`|\]\(((?:scripts|references|assets)\/[^)\s]+)\)/g;

function lineFindings(options: {
  readonly document: SkillDocument;
  readonly files: readonly string[];
}): readonly SkillFinding[] {
  const findings: SkillFinding[] = [];

  for (const line of options.document.bodyLines) {
    const tool = hostOnlyTools.exec(line.text)?.[0];

    if (tool !== undefined) {
      findings.push(
        finding({
          skill: options.document.name,
          line: line.number,
          rule: "host-tools",
          message: `${tool} exists on one host only, describe the action instead`,
        }),
      );
    }

    for (const match of line.text.matchAll(supportingReference)) {
      const reference = match[1] ?? match[2] ?? "";

      if (reference.split("/").length !== 2 || !options.files.includes(reference)) {
        findings.push(
          finding({
            skill: options.document.name,
            line: line.number,
            rule: "references",
            message: `${reference} must exist one folder down in the skill`,
          }),
        );
      }
    }
  }

  return findings;
}

function voiceFindings(document: SkillDocument): readonly SkillFinding[] {
  const hasBlock = document.bodyLines.some((line) => line.text === voiceBlock);

  if (hasBlock === document.voice) {
    return [];
  }

  return [
    finding({
      skill: document.name,
      line: document.voice ? document.voiceLine : document.bodyStartLine,
      rule: "voice",
      message: document.voice
        ? "add the voice block from src/skills/voiceBlock.ts as its own paragraph"
        : 'set metadata shadowclone-voice to "true" for a skill with the voice block',
    }),
  ];
}

export function skillQualityFindings(options: {
  readonly name: string;
  readonly text: string;
  readonly bundledNames: readonly string[];
  readonly files: readonly string[];
  readonly exemptions?: readonly SkillRule[];
}): readonly SkillFinding[] {
  const document = readSkillDocument(options.text);
  const exemptions = options.exemptions ?? [];

  if (document === null) {
    return [
      finding({
        skill: options.name,
        line: 1,
        rule: "document",
        message: "frontmatter does not parse",
      }),
    ];
  }

  const findings: readonly SkillFinding[] = [
    ...descriptionFindings({ document, bundledNames: options.bundledNames }),
    ...sectionFindings({ document, exemptions }),
    ...gateFindings(document),
    ...exampleFindings(document),
    ...completionFindings(document),
    ...lineFindings({ document, files: options.files }),
    ...nameFindings(document),
    ...appliesWhenFindings(document),
    ...bodyLengthFindings(document),
    ...voiceFindings(document),
  ];

  return findings.filter(
    (entry) => entry.rule === "document" || !exemptions.some((rule) => rule === entry.rule),
  );
}
