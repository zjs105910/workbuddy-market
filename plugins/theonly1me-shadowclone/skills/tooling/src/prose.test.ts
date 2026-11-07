import { expect, test } from "bun:test";
import { treeWith } from "./boundaries/testing";
import { checkProse } from "./prose";
import { listProseFiles } from "./prose/files";

const longSentence = `${Array.from({ length: 30 }, () => "word").join(" ")}.`;

test("a sentence over 25 words fails with the rule name and the line", async () => {
  const rootDirectory = await treeWith({
    "docs/guide.md": `# Guide\n\n${longSentence}\n`,
  });

  const report = await checkProse({ rootDirectory });

  expect(report.steErrors.map((finding) => [finding.file, finding.line, finding.rule])).toEqual([
    ["docs/guide.md", 3, "long-sentence"],
  ]);
});

test("a warning is counted and does not fail the file", async () => {
  const rootDirectory = await treeWith({
    "docs/guide.md": "# Guide\n\nThe file was copied by the tool.\n",
  });

  const report = await checkProse({ rootDirectory });

  expect(report.steErrors).toEqual([]);
  expect(report.warningCount).toBe(1);
});

test("a link to a missing file fails, and links to a file and a folder pass", async () => {
  const rootDirectory = await treeWith({
    "docs/guide.md": [
      "# Guide",
      "",
      "See [the other page](other.md), [the folder](../src/), and [a missing page](missing.md).",
      "",
    ].join("\n"),
    "docs/other.md": "# Other\n",
    "src/index.ts": "export {};\n",
  });

  const report = await checkProse({ rootDirectory });

  expect(report.linkProblems).toEqual([
    { file: "docs/guide.md", line: 3, message: "target missing.md does not exist" },
  ]);
});

test("an anchor must match a heading slug, with punctuation removed and duplicates numbered", async () => {
  const rootDirectory = await treeWith({
    "docs/guide.md": [
      "# Guide",
      "",
      "## Hello, World! And `code`",
      "",
      "## Repeat",
      "",
      "## Repeat",
      "",
      "Good: [one](#hello-world-and-code), [two](#repeat-1), [three](other.md#first-topic).",
      "",
      "Bad: [four](#hello), [five](other.md#second-topic).",
      "",
    ].join("\n"),
    "docs/other.md": "# Other\n\n## First topic\n",
  });

  const report = await checkProse({ rootDirectory });

  expect(report.linkProblems.map((problem) => [problem.line, problem.message])).toEqual([
    [11, "heading #hello does not exist in docs/guide.md"],
    [11, "heading #second-topic does not exist in docs/other.md"],
  ]);
});

test("external links and links inside code are not checked", async () => {
  const rootDirectory = await treeWith({
    "docs/guide.md": [
      "# Guide",
      "",
      "[site](https://example.com/missing) and `[code](missing.md)`.",
      "",
      "```md",
      "[fenced](missing.md)",
      "```",
      "",
    ].join("\n"),
  });

  const report = await checkProse({ rootDirectory });

  expect(report.linkProblems).toEqual([]);
});

test("excluded files are skipped and the data handling skill is checked", async () => {
  const bad = `# Bad\n\n${longSentence}\n\n[gone](gone.md)\n`;
  const rootDirectory = await treeWith({
    "README.md": "# Readme\n",
    "CHANGELOG.md": bad,
    "node_modules/pkg/README.md": bad,
    "skills/example/SKILL.md": bad,
    "preferences/example.md": bad,
    ".agents/skills/example/SKILL.md": bad,
    ".claude/skills/other/SKILL.md": bad,
    "packages/builds/src/fixtures/sample.md": bad,
    "evals/no-comments/task/prompt.md": bad,
    "evals/no-comments/graders/rubric.md": bad,
    ".claude/skills/data-handling/SKILL.md": bad,
  });

  expect(await listProseFiles({ rootDirectory })).toEqual([
    ".claude/skills/data-handling/SKILL.md",
    "README.md",
  ]);

  const report = await checkProse({ rootDirectory });

  expect(report.steErrors.map((finding) => finding.file)).toEqual([
    ".claude/skills/data-handling/SKILL.md",
  ]);
  expect(report.linkProblems.map((problem) => problem.file)).toEqual([
    ".claude/skills/data-handling/SKILL.md",
  ]);
});
