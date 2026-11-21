import { expect, test } from "bun:test";
import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { sampleSkillText } from "@shadowclone/skills/testing";
import { voiceBlock } from "@shadowclone/skills";
import { findSkillQualityViolations } from "./skills";

const sharedSentence =
  "Every report names the command that ran and the exit code it returned to the user.";

async function treeWith(files: Record<string, string>): Promise<string> {
  const rootDirectory = await mkdtemp(path.join(os.tmpdir(), "shadowclone-skill-quality-"));

  for (const [file, text] of Object.entries(files)) {
    await Bun.write(path.join(rootDirectory, file), text);
  }

  return rootDirectory;
}

const fixtureSentences = [
  "The work is ready for a final check.",
  "A summary line said two agents were installed.",
  "The command still printed the wrong count.",
  "Run the command and read the summary line.",
  "The rerun printed one agent installed and exit code 0.",
  "The output line that shows the result.",
] as const;

function skill(options: { readonly name: string; readonly alternative: string }): string {
  return fixtureSentences.reduce(
    (text, sentence) => text.replace(sentence, `${sentence.slice(0, -1)} in ${options.name}.`),
    sampleSkillText(options),
  );
}

test("the repository's bundled skills pass, with pending skills skipped", async () => {
  const report = await findSkillQualityViolations({
    rootDirectory: path.resolve(import.meta.dir, "../.."),
  });

  expect(report.findings).toEqual([]);
  expect(report.checkedSkillCount).toBeGreaterThan(0);
});

test("a pending skill that meets the bar must leave the pending list", async () => {
  const rootDirectory = await treeWith({
    "skills/check-real-output/SKILL.md": skill({
      name: "check-real-output",
      alternative: "write-real-tests",
    }),
    "skills/write-real-tests/SKILL.md": skill({
      name: "write-real-tests",
      alternative: "check-real-output",
    }),
  });

  const report = await findSkillQualityViolations({
    rootDirectory,
    pending: new Set(["write-real-tests", "retired-skill"]),
    exemptions: new Map(),
  });

  expect(
    report.findings.map((finding) => `${finding.skill} ${finding.rule} ${finding.message}`),
  ).toEqual([
    "retired-skill pending-list is not a bundled skill, remove it from pendingSkillNames",
    "write-real-tests pending-list meets the bar, remove it from pendingSkillNames",
  ]);
});

test("a sentence shared by three skills is flagged, and two skills may share one", async () => {
  const names = ["check-real-output", "write-real-tests", "plan-real-work"];
  const files = Object.fromEntries(
    names.map((name, index) => [
      `skills/${name}/SKILL.md`,
      skill({ name, alternative: names[(index + 1) % names.length] ?? "" }).replace(
        "Keep the check read-only.",
        `Keep the check read-only for ${name}. ${index < 3 ? sharedSentence : ""}`,
      ),
    ]),
  );
  const shared = await findSkillQualityViolations({
    rootDirectory: await treeWith(files),
    pending: new Set(),
    exemptions: new Map(),
  });
  const pairOnly = await findSkillQualityViolations({
    rootDirectory: await treeWith({
      ...files,
      "skills/plan-real-work/SKILL.md": skill({
        name: "plan-real-work",
        alternative: "check-real-output",
      }).replace("Keep the check read-only.", "Keep the check read-only for plan-real-work."),
    }),
    pending: new Set(),
    exemptions: new Map(),
  });

  expect(shared.findings.map((finding) => finding.rule)).toEqual(
    expect.arrayContaining(["repeated-sentence"]),
  );
  expect(pairOnly.findings.filter((finding) => finding.rule === "repeated-sentence")).toEqual([]);
});

test("a bundled script needs only node modules and its own test", async () => {
  const text = skill({ name: "check-real-output", alternative: "write-real-tests" }).replace(
    "Keep the check read-only.",
    "Run `scripts/check.mjs` on the changed files.",
  );
  const files = {
    "skills/check-real-output/SKILL.md": text,
    "skills/write-real-tests/SKILL.md": skill({
      name: "write-real-tests",
      alternative: "check-real-output",
    }),
  };
  const failing = await findSkillQualityViolations({
    rootDirectory: await treeWith({
      ...files,
      "skills/check-real-output/scripts/check.mjs":
        'import chalk from "chalk";\nimport { readFile } from "node:fs/promises";\n',
    }),
    pending: new Set(),
    exemptions: new Map(),
  });
  const passing = await findSkillQualityViolations({
    rootDirectory: await treeWith({
      ...files,
      "skills/check-real-output/scripts/check.mjs":
        'import { readFile } from "node:fs/promises";\n',
      "packages/skills/src/skills/scripts/check-real-output.check.test.ts": "export {};\n",
    }),
    pending: new Set(),
    exemptions: new Map(),
  });

  expect(failing.findings.map((finding) => finding.message)).toEqual([
    "scripts/check.mjs imports chalk, use only node: modules",
    "scripts/check.mjs needs a test at packages/skills/src/skills/scripts/check-real-output.check.test.ts",
  ]);
  expect(passing.findings).toEqual([]);
});

test("a finished skill with a long sentence fails the plain-English check", async () => {
  const longSentence = `${Array.from({ length: 30 }, (_, index) => `word${index}`).join(" ")}.`;
  const files = {
    "skills/check-real-output/SKILL.md": skill({
      name: "check-real-output",
      alternative: "write-real-tests",
    }).replace("Keep the check read-only.", `Keep the check read-only. ${longSentence}`),
    "skills/write-real-tests/SKILL.md": skill({
      name: "write-real-tests",
      alternative: "check-real-output",
    }),
  };
  const rootDirectory = await treeWith(files);
  const finished = await findSkillQualityViolations({
    rootDirectory,
    pending: new Set(),
    exemptions: new Map(),
  });
  const pending = await findSkillQualityViolations({
    rootDirectory,
    pending: new Set(["check-real-output"]),
    exemptions: new Map(),
  });

  expect(finished.findings.map((finding) => `${finding.skill} ${finding.rule}`)).toEqual([
    "check-real-output plain-english",
  ]);
  expect(pending.findings).toEqual([]);
});

test("the voice block may repeat in every skill that writes for the user", async () => {
  const names = ["check-real-output", "write-real-tests", "plan-real-work"];
  const files = Object.fromEntries(
    names.map((name, index) => [
      `skills/${name}/SKILL.md`,
      skill({ name, alternative: names[(index + 1) % names.length] ?? "" })
        .replace(
          "  shadowclone-applies-when: before you say the work is done",
          '  shadowclone-applies-when: before you say the work is done\n  shadowclone-voice: "true"',
        )
        .replace("Keep the check read-only.", `Keep the check read-only for ${name}.\n\n${voiceBlock}`),
    ]),
  );
  const report = await findSkillQualityViolations({
    rootDirectory: await treeWith(files),
    pending: new Set(),
    exemptions: new Map(),
  });

  expect(report.findings).toEqual([]);
});

test("a permanent plain-English exemption skips the checker for that skill only", async () => {
  const longSentence = `${Array.from({ length: 30 }, (_, index) => `word${index}`).join(" ")}.`;
  const names = ["check-real-output", "write-real-tests"];
  const rootDirectory = await treeWith(
    Object.fromEntries(
      names.map((name, index) => [
        `skills/${name}/SKILL.md`,
        skill({ name, alternative: names[(index + 1) % names.length] ?? "" }).replace(
          "Keep the check read-only.",
          `Keep the check read-only. ${longSentence}`,
        ),
      ]),
    ),
  );
  const report = await findSkillQualityViolations({
    rootDirectory,
    pending: new Set(),
    exemptions: new Map([["check-real-output", ["plain-english"]]]),
  });

  expect(report.findings.map((finding) => `${finding.skill} ${finding.rule}`)).toEqual([
    "write-real-tests plain-english",
  ]);
});
