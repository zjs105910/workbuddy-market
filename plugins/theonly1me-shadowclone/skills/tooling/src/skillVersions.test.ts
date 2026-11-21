import { expect, test } from "bun:test";
import { mkdtemp, realpath } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { format } from "prettier";
import { fingerprint } from "@shadowclone/core";
import { recordSkillVersions, unrecordedSkillVersions } from "./skillVersions";

const versionsFile = "packages/skills/src/skills/bundledVersions.json";

async function treeWith(files: Record<string, string>): Promise<string> {
  const rootDirectory = await realpath(
    await mkdtemp(path.join(os.tmpdir(), "shadowclone-skill-versions-")),
  );

  for (const [file, text] of Object.entries(files)) {
    await Bun.write(path.join(rootDirectory, file), text);
  }

  return rootDirectory;
}

test("every bundled skill file in the repository has its version recorded", async () => {
  expect(await unrecordedSkillVersions(path.resolve(import.meta.dir, "../.."))).toEqual([]);
});

test("a changed skill file is reported, and recording keeps every earlier version", async () => {
  const oldVersion = fingerprint("---\nname: check-output\n---\nOld text.\n");
  const skillText = "---\nname: check-output\n---\nNew text.\n";
  const script = 'console.log("check");\n';
  const rootDirectory = await treeWith({
    "skills/check-output/SKILL.md": skillText,
    "skills/check-output/scripts/check.mjs": script,
    [versionsFile]: JSON.stringify({ "check-output": { "SKILL.md": [oldVersion] } }),
  });

  expect(await unrecordedSkillVersions(rootDirectory)).toEqual([
    {
      skill: "check-output",
      file: "scripts/check.mjs",
      fingerprint: fingerprint(Buffer.from(script).toString("base64")),
    },
    {
      skill: "check-output",
      file: "SKILL.md",
      fingerprint: fingerprint(skillText),
    },
  ]);
  expect(await recordSkillVersions(rootDirectory)).toBe(2);

  const written = await Bun.file(path.join(rootDirectory, versionsFile)).text();

  expect(JSON.parse(written)).toEqual({
    "check-output": {
      "SKILL.md": [oldVersion, fingerprint(skillText)],
      "scripts/check.mjs": [fingerprint(Buffer.from(script).toString("base64"))],
    },
  });
  expect(await format(written, { parser: "json", printWidth: 100 })).toBe(written);
  expect(await unrecordedSkillVersions(rootDirectory)).toEqual([]);
});
