import { expect, test } from "bun:test";
import { parseProfileBlocks } from "@shadowclone/profile";
import { renderFeatureWorkflowSkill } from "@shadowclone/harness";
import {
  nestMarkdownHeadings,
  type RepositoryGuidanceSource,
  transformRepositoryGuidance,
} from "@shadowclone/learning";

function skillSource(): RepositoryGuidanceSource {
  return {
    relativePath: ".claude/skills/review/SKILL.md",
    filePath: "/unused",
    byteLength: 1,
    kind: "skill",
  };
}

test("keeps one skill file inside one profile rule", () => {
  const transformed = transformRepositoryGuidance({
    source: skillSource(),
    redactedText: [
      "---",
      "name: review",
      "description: Review changes",
      "---",
      "# Review carefully",
      "",
      "## Correctness",
      "",
      "```md",
      "## This is an example",
      "```",
    ].join("\n"),
  });

  expect(transformed?.title).toBe("Repository skill: Review carefully");
  expect(transformed?.body).not.toContain("name: review");
  expect(transformed?.body).toContain("### Review carefully");
  expect(transformed?.body).toContain("#### Correctness");
  expect(transformed?.body).toContain("## This is an example");

  const profile = `## ${transformed?.title}\n\n${transformed?.body}`;

  expect(parseProfileBlocks(profile)).toHaveLength(1);
});

test("does not treat fenced headings as a skill title", () => {
  const transformed = transformRepositoryGuidance({
    source: skillSource(),
    redactedText: "```md\n# Example\n```\nUse this guidance.",
  });

  expect(transformed?.title).toBe("Repository skill: Imported guidance");
});

test("nests headings without changing fenced code", () => {
  const input = "# Root\n~~~markdown\n## Example\n~~~\n###### Deep";

  expect(nestMarkdownHeadings(input)).toBe(
    "### Root\n~~~markdown\n## Example\n~~~\n###### Deep",
  );
});

test("closes an unfinished fence before profile metadata", () => {
  expect(nestMarkdownHeadings("```md\n## Example")).toBe(
    "```md\n## Example\n```",
  );
});

test("import never reads back the harness Shadowclone writes", () => {
  const skill = renderFeatureWorkflowSkill({ gate: null });

  expect(
    transformRepositoryGuidance({
      source: skillSource(),
      redactedText: skill.text,
    }),
  ).toBeNull();

  const agents = transformRepositoryGuidance({
    source: {
      relativePath: "AGENTS.md",
      filePath: "/unused",
      byteLength: 1,
      kind: "instructions",
    },
    redactedText:
      "# Team\n\nUse the shared queue.\n\n<!-- shadowclone-harness:start -->\n## Working in this repository\n\n- Small files: Keep every file under 200 lines.\n<!-- shadowclone-harness:end -->\n",
  });

  expect(agents?.body).toContain("Use the shared queue.");
  expect(agents?.body).not.toContain("Small files");
});
