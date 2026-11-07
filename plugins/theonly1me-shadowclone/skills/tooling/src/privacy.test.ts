import { expect, test } from "bun:test";
import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { findPrivacyFindings, hashTerm, normalizeTerm } from "./privacy";

async function treeWith(files: Record<string, string>): Promise<string> {
  const rootDirectory = await mkdtemp(path.join(os.tmpdir(), "shadowclone-privacy-"));

  for (const [file, text] of Object.entries(files)) {
    await Bun.write(path.join(rootDirectory, file), text);
  }

  return rootDirectory;
}

function described(findings: readonly { file: string; line: number; rule: string }[]) {
  return findings.map((finding) => `${finding.file}:${finding.line} ${finding.rule}`);
}

test("the repository's shipped guidance has no private material", async () => {
  const report = await findPrivacyFindings({ rootDirectory: path.resolve(import.meta.dir, "../..") });

  expect(report.findings).toEqual([]);
  expect(report.checkedFileCount).toBeGreaterThan(0);
});

test("flags an address, a machine path, an issue reference, and an unlisted URL on their lines", async () => {
  const rootDirectory = await treeWith({
    "skills/sample-skill/SKILL.md": [
      "# Sample",
      "Ask dana@corp.dev before merging.",
      "Logs live in /Users/dana/work.",
      "See acme/billing#42 for context.",
      "Read https://intranet.acme.dev/wiki first.",
      "",
    ].join("\n"),
  });

  const report = await findPrivacyFindings({ rootDirectory, privateTerms: [] });

  expect(described(report.findings)).toEqual([
    "skills/sample-skill/SKILL.md:2 email",
    "skills/sample-skill/SKILL.md:3 home-path",
    "skills/sample-skill/SKILL.md:4 issue-reference",
    "skills/sample-skill/SKILL.md:5 url",
  ]);
});

test("allows listed documentation URLs, example addresses, and paths written with ~", async () => {
  const rootDirectory = await treeWith({
    "skills/sample-skill/SKILL.md": [
      "Read https://code.claude.com/docs/en/skills and https://agentskills.io/specification.",
      "Write to user@example.com or clone git@github.com:owner/repository.git.",
      "Save the file in ~/.agents/voice.md.",
      "",
    ].join("\n"),
  });

  expect((await findPrivacyFindings({ rootDirectory, privateTerms: [] })).findings).toEqual([]);
});

test("flags a gendered pronoun in skill prose but not inside a script", async () => {
  const rootDirectory = await treeWith({
    "skills/sample-skill/SKILL.md": "Ask the user before he merges.\n",
    "skills/sample-skill/scripts/check.mjs": 'export const label = "her";\n',
  });

  expect(
    described((await findPrivacyFindings({ rootDirectory, privateTerms: [] })).findings),
  ).toEqual(["skills/sample-skill/SKILL.md:1 pronoun"]);
});

test("flags a private phrase by its hash, across case and spacing", async () => {
  const rootDirectory = await treeWith({
    "preferences/sample.md": "Follow the Acme   Rocket conventions.\nThe acme team agrees.\n",
  });

  const report = await findPrivacyFindings({ rootDirectory, privateTerms: ["acme rocket"] });

  expect(described(report.findings)).toEqual(["preferences/sample.md:1 private-term"]);
  expect(normalizeTerm("  ACME   Rocket! ")).toBe("acme rocket");
  expect(hashTerm("Acme Rocket")).toBe(hashTerm("acme rocket"));
  expect(hashTerm("acme rocket")).not.toBe(hashTerm("acme"));
});

test("reads only the shipped folders", async () => {
  const rootDirectory = await treeWith({
    "docs/notes.md": "Ask dana@corp.dev.\n",
    "plugins/shadowclone/skills/setup/SKILL.md": "Ask dana@corp.dev.\n",
  });

  expect(
    described((await findPrivacyFindings({ rootDirectory, privateTerms: [] })).findings),
  ).toEqual(["plugins/shadowclone/skills/setup/SKILL.md:1 email"]);
});
