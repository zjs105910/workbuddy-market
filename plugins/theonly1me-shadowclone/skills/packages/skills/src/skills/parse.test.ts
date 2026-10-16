import { expect, test } from "bun:test";
import {
  parseSeedAgentSkillDocument,
  parseSeedPreferenceDocument,
} from "./parse";

function agentSkill(
  options: {
    readonly name?: string;
    readonly metadata?: readonly string[];
    readonly sections?: readonly string[];
  } = {},
): string {
  const name = options.name ?? "focused-review";

  return [
    "---",
    `name: ${name}`,
    "description: Review one change against a concrete contract and report actionable findings.",
    "metadata:",
    ...(options.metadata ?? [
      "  shadowclone-category: review",
      "  shadowclone-section: workflow",
      "  shadowclone-applies-when: reviewing a completed change",
    ]),
    "---",
    "# Focused Review",
    "",
    ...(options.sections ?? [
      "## Use when",
      "",
      "Reviewing one change.",
      "",
      "## Process",
      "",
      "1. Read the contract and diff.",
      "",
      "## Guardrails",
      "",
      "Report only reachable defects.",
      "",
      "## Completion",
      "",
      "Every finding cites evidence.",
    ]),
  ].join("\n");
}

test("rejects unknown standard Agent Skill frontmatter", () => {
  expect(() =>
    parseSeedAgentSkillDocument({
      directoryName: "focused-review",
      text: agentSkill().replace("metadata:\n", "command: review\nmetadata:\n"),
    }),
  ).toThrow("Invalid Agent Skill metadata in focused-review/SKILL.md");
});

test("rejects invalid Shadowclone metadata", () => {
  expect(() =>
    parseSeedAgentSkillDocument({
      directoryName: "focused-review",
      text: agentSkill({
        metadata: [
          "  shadowclone-category: Review Work",
          "  shadowclone-section: workflow",
          "  shadowclone-applies-when: reviewing a completed change",
        ],
      }),
    }),
  ).toThrow("Invalid Agent Skill metadata in focused-review/SKILL.md");
});

test("rejects a directory that disagrees with the skill name", () => {
  expect(() =>
    parseSeedAgentSkillDocument({
      directoryName: "another-name",
      text: agentSkill(),
    }),
  ).toThrow("Agent Skill directory does not match its name");
});

test("rejects an incomplete Agent Skill workflow", () => {
  expect(() =>
    parseSeedAgentSkillDocument({
      directoryName: "focused-review",
      text: agentSkill({
        sections: [
          "## Use when",
          "Reviewing one change.",
          "## Process",
          "1. Read the diff.",
          "## Completion",
          "Every finding cites evidence.",
        ],
      }),
    }),
  ).toThrow("Agent Skill workflow is incomplete");
});

test("rejects duplicate nested metadata before YAML replaces it", () => {
  expect(() =>
    parseSeedAgentSkillDocument({
      directoryName: "focused-review",
      text: agentSkill({
        metadata: [
          "  shadowclone-category: testing",
          "  shadowclone-category: review",
          "  shadowclone-section: workflow",
          "  shadowclone-applies-when: reviewing a completed change",
        ],
      }),
    }),
  ).toThrow("Duplicate seed metadata in focused-review/SKILL.md");
});

test("keeps preference documents separate from Agent Skills", () => {
  const preference = parseSeedPreferenceDocument({
    filename: "questions-early.md",
    text: [
      "---",
      "id: questions-early",
      "title: Ask when intent is unclear",
      "axis: question-frequency",
      "category: communication",
      "section: workflow",
      "applies-when:",
      "  - finding multiple plausible interpretations",
      "---",
      "## Ask when intent is unclear",
      "",
      "Ask before choosing between materially different outcomes.",
    ].join("\n"),
  });

  expect(preference.kind).toBe("preference");
  expect(preference.axis).toBe("question-frequency");
});
