import { expect, test } from "bun:test";
import { mkdtemp, readdir, realpath } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { replaceLocalText } from "./index";

async function home(): Promise<string> {
  return realpath(await mkdtemp(path.join(os.tmpdir(), "shadowclone-folders-")));
}

async function remove(filePath: string): Promise<void> {
  await replaceLocalText({ filePath, previous: await Bun.file(filePath).text(), next: null });
}

test("deleting the last files of a skill removes its folder, and the skills root stays", async () => {
  const root = path.join(await home(), ".claude/skills");
  const skill = path.join(root, "demo-skill");

  await Bun.write(path.join(skill, "SKILL.md"), "skill\n");
  await Bun.write(path.join(skill, "scripts/check.mjs"), "export {};\n");
  await Bun.write(path.join(root, "other-skill/SKILL.md"), "other\n");

  await remove(path.join(skill, "SKILL.md"));
  await remove(path.join(skill, "scripts/check.mjs"));

  expect(await readdir(root)).toEqual(["other-skill"]);
});

test("a skill folder with a file that the user added stays", async () => {
  const skill = path.join(await home(), ".agents/skills/demo-skill");

  await Bun.write(path.join(skill, "SKILL.md"), "skill\n");
  await Bun.write(path.join(skill, "notes.md"), "mine\n");

  await remove(path.join(skill, "SKILL.md"));

  expect(await readdir(skill)).toEqual(["notes.md"]);
});

test("a folder outside a skill root stays empty instead of being removed", async () => {
  const source = path.join(await home(), "skills/project/src");

  await Bun.write(path.join(source, "generated.md"), "text\n");

  await remove(path.join(source, "generated.md"));

  expect(await readdir(source)).toEqual([]);
});
