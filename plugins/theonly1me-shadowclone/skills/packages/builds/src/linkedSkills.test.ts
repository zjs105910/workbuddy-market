import { expect, test } from "bun:test";
import { mkdir, mkdtemp, readlink, realpath, symlink } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { defaultConfig, writeConfig } from "@shadowclone/core";
import { writeMaintenanceState } from "@shadowclone/skills";
import { applyBuild } from "./apply";
import { buildCatalog } from "./catalog";
import { buildFixture, buildInput } from "./testing";
import { previewBuild } from "./plan";

const skillText = '---\nname: careful-review\ndescription: "Use when reviewing a change before handoff."\n---\n\nRead the whole diff.\n';

async function sharedSkillHome(options: { readonly claudeTarget: (home: string) => Promise<string> }) {
  const context = await buildFixture();
  const home = path.dirname(context.paths.shadowcloneDirectory);
  const source = path.join(home, ".agents/skills/careful-review");
  const claudeLink = path.join(home, ".claude/skills/careful-review");
  const geminiLink = path.join(home, ".gemini/config/skills/careful-review");

  await writeConfig({
    config: { ...defaultConfig, sources: { ...defaultConfig.sources, "skill-library": true } },
    configPath: context.paths.configFile,
  });
  await Bun.write(path.join(source, "SKILL.md"), skillText);
  await mkdir(path.dirname(claudeLink), { recursive: true });
  await mkdir(path.dirname(geminiLink), { recursive: true });
  await symlink(await options.claudeTarget(home), claudeLink);
  await symlink(source, geminiLink);
  await writeMaintenanceState({
    paths: context.paths,
    state: {
      version: 1,
      roots: [".agents/skills", ".claude/skills"].map((relative, index) => ({
        id: String(index).repeat(64),
        directory: path.join(home, relative),
        cwd: home,
        scope: "global" as const,
        owner: "user" as const,
        destination: path.join(home, relative),
        enabled: true,
      })),
      tracked: [],
      assessed: {},
      findings: {},
      rejected: {},
    },
  });

  const item = (await buildCatalog({ ...context, scope: "global" })).find((entry) => entry.name === "careful-review");

  if (!item) throw new Error("The user skill was not discovered");

  return { context, home, source, claudeLink, geminiLink, input: buildInput({ choices: { [item.id]: true } }) };
}

test("equipping a user skill that other agents read through links to its source writes nothing through the links", async () => {
  const setup = await sharedSkillHome({ claudeTarget: async (home) => path.join(home, ".agents/skills/careful-review") });
  const plan = await previewBuild({ ...setup.context, input: setup.input });

  expect(plan.updates.map((update) => update.filePath).filter((filePath) => filePath.includes("careful-review"))).toEqual([]);
  expect(plan.warnings.filter((warning) => warning.includes("careful-review"))).toEqual([]);

  await applyBuild({ ...setup.context, plan });

  expect(await readlink(setup.claudeLink)).toBe(setup.source);
  expect(await readlink(setup.geminiLink)).toBe(setup.source);
  expect(await Bun.file(path.join(setup.source, "SKILL.md")).text()).toBe(skillText);
});

test("a skill folder that links somewhere else is skipped and named in the review", async () => {
  const elsewhere = path.join(await realpath(await mkdtemp(path.join(os.tmpdir(), "shadowclone-elsewhere-"))), "careful-review");
  const setup = await sharedSkillHome({ claudeTarget: async () => elsewhere });

  await Bun.write(path.join(elsewhere, "SKILL.md"), "An unrelated skill.\n");

  const plan = await previewBuild({ ...setup.context, input: setup.input });

  expect(plan.updates.some((update) => update.filePath.startsWith(setup.claudeLink))).toBeFalse();
  expect(plan.warnings).toContain(
    `~/.claude/skills/careful-review is a link to ${elsewhere}. Shadowclone does not write through links, so the agent that reads ~/.claude/skills/careful-review does not get careful-review from this build.`,
  );

  await applyBuild({ ...setup.context, plan });

  expect(await Bun.file(path.join(elsewhere, "SKILL.md")).text()).toBe("An unrelated skill.\n");
});
