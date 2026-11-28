import { expect, test } from "bun:test";
import { skillQualityFindings } from "./quality";
import { sampleSkillText } from "./qualityFixtures";
import { voiceBlock } from "./voiceBlock";

const bundledNames = ["check-real-output", "write-real-tests"];
const goodText = sampleSkillText({ name: "check-real-output", alternative: "write-real-tests" });

function findingsFor(options: { readonly text: string; readonly files?: readonly string[] }) {
  return skillQualityFindings({
    name: "check-real-output",
    text: options.text,
    bundledNames,
    files: options.files ?? ["SKILL.md"],
  });
}

function rulesFor(text: string) {
  return findingsFor({ text }).map((finding) => finding.rule);
}

function lineOf(options: { readonly text: string; readonly fragment: string }): number {
  return options.text.split("\n").findIndex((line) => line.includes(options.fragment)) + 1;
}

test("a skill that meets the bar has no findings", () => {
  expect(findingsFor({ text: goodText })).toEqual([]);
});

test("a description without user phrases or a Not for line is flagged", () => {
  const text = goodText
    .replace('says "make sure it works" or "check this before merging"', "asks for a check")
    .replace(" Not for writing new tests (use `write-real-tests`).", " It stays read-only.");

  expect(findingsFor({ text }).map((finding) => finding.message)).toEqual([
    "quote at least two phrases a user says",
    'end with "Not for ... (use `<skill>`)."',
  ]);
});

test("a Not for line must name another bundled skill", () => {
  const missing = goodText.replace("(use `write-real-tests`)", "(use `missing-skill`)");
  const itself = goodText.replace("(use `write-real-tests`)", "(use `check-real-output`)");

  expect(rulesFor(missing)).toEqual(["description"]);
  expect(rulesFor(itself)).toEqual(["description"]);
});

test("sections out of order are flagged", () => {
  const gates =
    "## Gates\n\n1. Run the command the user runs.\n2. Read every line of its output.\n3. Report the exit code.\n\n";
  const process =
    "## Process\n\n1. Run the command in a throwaway home.\n2. Compare each count with what happened.\n\n";
  const swapped = goodText.replace(gates + process, process + gates);

  expect(swapped).not.toBe(goodText);
  expect(rulesFor(swapped)).toEqual(["sections"]);
});

test("gates that end after the first 40 body lines are flagged", () => {
  const padded = goodText.replace(
    "The work is ready for a final check.",
    Array.from({ length: 40 }, (_, index) => `Context line ${index + 1}.`).join("\n"),
  );

  expect(rulesFor(padded)).toEqual(["gates"]);
});

test("fewer than three gates are flagged", () => {
  expect(rulesFor(goodText.replace("3. Report the exit code.\n", ""))).toEqual(["gates"]);
});

test("an example without all five labels is flagged", () => {
  const text = goodText.replace(
    "**Hidden cost:** The command still printed the wrong count.\n",
    "",
  );

  expect(findingsFor({ text }).map((finding) => finding.message)).toEqual(["add **Hidden cost:**"]);
});

test("a completion with seven report items is flagged", () => {
  const items = Array.from({ length: 7 }, (_, index) => `- Item ${index + 1}.`).join("\n");
  const text = goodText.replace(
    "- The command and its exit code.\n- The output line that shows the result.",
    items,
  );

  expect(rulesFor(text)).toEqual(["completion"]);
});

test("a host-only tool name is flagged on its own line", () => {
  const text = goodText.replace(
    "2. Compare each count with what happened.",
    "2. Ask with AskUserQuestion when unsure.",
  );
  const [finding] = findingsFor({ text });

  expect(finding?.rule).toBe("host-tools");
  expect(finding?.line).toBe(lineOf({ text, fragment: "AskUserQuestion" }));
});

test("a supporting file must exist one folder down in the skill", () => {
  const text = goodText.replace(
    "Keep the check read-only.",
    "Run `scripts/check.mjs` and `scripts/deep/run.mjs`.",
  );

  expect(findingsFor({ text, files: ["SKILL.md"] }).map((finding) => finding.message)).toEqual([
    "scripts/check.mjs must exist one folder down in the skill",
    "scripts/deep/run.mjs must exist one folder down in the skill",
  ]);
  expect(
    findingsFor({ text, files: ["SKILL.md", "scripts/check.mjs", "scripts/deep/run.mjs"] }).map(
      (finding) => finding.message,
    ),
  ).toEqual(["scripts/deep/run.mjs must exist one folder down in the skill"]);
});

test("a body over 150 lines is flagged", () => {
  const text = goodText.replace(
    "Keep the check read-only.",
    Array.from({ length: 120 }, (_, index) => `Guardrail ${index + 1}.`).join("\n"),
  );

  expect(rulesFor(text)).toEqual(["body-length"]);
});

test("an applies-when that is not a short moment is flagged", () => {
  const text = goodText.replace(
    "shadowclone-applies-when: before you say the work is done",
    "shadowclone-applies-when: preparing completed work for review or handoff",
  );

  expect(rulesFor(text)).toEqual(["applies-when"]);
});

test("a one-word or reserved name is flagged", () => {
  const findings = skillQualityFindings({
    name: "planning",
    text: goodText.replace("name: check-real-output", "name: planning"),
    bundledNames: ["planning", "write-real-tests"],
    files: ["SKILL.md"],
  });

  expect(findings.map((finding) => finding.rule)).toEqual(["name"]);
});

test("an exempted rule is not reported, and its section may be absent", () => {
  const withoutGates = goodText.replace(
    "## Gates\n\n1. Run the command the user runs.\n2. Read every line of its output.\n3. Report the exit code.\n\n",
    "",
  );
  const exempted = skillQualityFindings({
    name: "check-real-output",
    text: withoutGates,
    bundledNames,
    files: ["SKILL.md"],
    exemptions: ["gates"],
  });

  expect(rulesFor(withoutGates)).toEqual(["sections"]);
  expect(exempted).toEqual([]);
});

test("a document whose frontmatter does not parse is flagged once", () => {
  expect(rulesFor("# No frontmatter\n")).toEqual(["document"]);
});

test("a skill has the voice block exactly when its voice metadata says so", () => {
  const withMetadata = goodText.replace(
    "  shadowclone-applies-when: before you say the work is done",
    '  shadowclone-applies-when: before you say the work is done\n  shadowclone-voice: "true"',
  );
  const withBlock = (text: string) =>
    text.replace("Keep the check read-only.", `Keep the check read-only.\n\n${voiceBlock}`);

  expect(rulesFor(withMetadata)).toEqual(["voice"]);
  expect(rulesFor(withBlock(goodText))).toEqual(["voice"]);
  expect(rulesFor(withBlock(withMetadata))).toEqual([]);
});
