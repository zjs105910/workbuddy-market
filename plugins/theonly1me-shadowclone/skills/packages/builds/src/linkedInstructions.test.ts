import { expect, test } from "bun:test";
import { mkdir, readlink, symlink } from "node:fs/promises";
import path from "node:path";
import { applyBuild } from "./apply";
import { buildFixture, buildInput } from "./testing";
import { previewBuild } from "./plan";
import { undoRevision } from "@shadowclone/environment";

const masterText = "# My instructions\n\nKeep answers short.\n";

async function sharedInstructionsHome() {
  const context = await buildFixture();
  const home = path.dirname(context.paths.shadowcloneDirectory);
  const master = path.join(home, ".agents/AGENTS.md");
  const codex = path.join(home, ".codex/AGENTS.md");
  const claude = path.join(home, ".claude/CLAUDE.md");

  await Bun.write(master, masterText);
  await Bun.write(claude, "@~/.agents/AGENTS.md\n");
  await mkdir(path.dirname(codex), { recursive: true });
  await symlink(master, codex);

  return { context, master, codex, claude };
}

test("the wizard writes one routing block into the file that Codex links to and Claude Code imports", async () => {
  const setup = await sharedInstructionsHome();
  const plan = await previewBuild({ ...setup.context, input: buildInput() });
  const changed = plan.updates.map((update) => update.filePath);

  expect(changed).toContain(setup.master);
  expect(changed).not.toContain(setup.codex);
  expect(changed).not.toContain(setup.claude);

  const revision = await applyBuild({ ...setup.context, plan });
  const master = await Bun.file(setup.master).text();

  expect(master.startsWith(masterText)).toBeTrue();
  expect(master.match(/<shadowclone-guidance>/g)).toHaveLength(1);
  expect(master).toContain(": tests-that-catch-bugs");
  expect(await Bun.file(setup.claude).text()).toBe("@~/.agents/AGENTS.md\n");
  expect(await readlink(setup.codex)).toBe(setup.master);

  if (revision === null) throw new Error("The build did not record a revision");

  await undoRevision({ paths: setup.context.paths, id: revision });

  expect(await Bun.file(setup.master).text()).toBe(masterText);
  expect(await readlink(setup.codex)).toBe(setup.master);
});

test("Claude Code keeps its own block when CLAUDE.md does not import the linked file", async () => {
  const setup = await sharedInstructionsHome();

  await Bun.write(setup.claude, "# Claude notes\n");

  const plan = await previewBuild({ ...setup.context, input: buildInput() });

  await applyBuild({ ...setup.context, plan });

  expect(await Bun.file(setup.claude).text()).toContain("<shadowclone-guidance>");
  expect((await Bun.file(setup.master).text()).match(/<shadowclone-guidance>/g)).toHaveLength(1);
});
