import { expect, test } from "bun:test";
import { mkdir, mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { remainingEpisodes } from "./deep";
import { scriptedWizardAnswer } from "./firstTime";
import { captureArm } from "./freeze";
import { copyPersonalLibrary } from "./library";

test("the scripted build answers each axis and the optional skills", () => {
  const guidance = (id: string) => ({ id, title: id });
  const library = {
    axes: [{ id: "testing-approach", guidance: [guidance("testing-first"), guidance("testing-risk-based")] }],
    independentSkills: [guidance("verify-and-review"), guidance("prove-regression-tests")],
  };
  const answer = scriptedWizardAnswer({
    library,
    build: ["testing-first", "prove-regression-tests"],
  });

  expect(answer("Choose one for testing-approach: ")).toBe("1");
  expect(answer("Choose optional skills: ")).toBe("2");
  expect(() => answer("Something else")).toThrow("Unexpected wizard question");
});

test("reads the remaining backlog from learning output", () => {
  expect(remainingEpisodes(["\n  Deep learning covered 30 episode(s); 12 remain. Run shadowclone learn --deep again to continue."])).toBe(12);
  expect(remainingEpisodes(["Skill maintenance: 1 synced, 2 updated, 0 pending, 0 deferred, 0 conflicts."])).toBe(0);
});

test("copies the personal library without Shadowclone skills and freezes portable paths", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "study-prepare-"));

  try {
    const source = path.join(root, "source");
    const home = path.join(root, "home");
    const workspace = path.join(root, "workspace");
    await Bun.write(path.join(source, ".agents/skills/names/SKILL.md"), `---\nname: names\n---\nSee ${source}/.agents/skills/names/rules.md.\n`);
    await Bun.write(path.join(source, ".agents/skills/names/rules.md"), "Use full words.\n");
    await Bun.write(path.join(source, ".agents/skills/shadowclone-baseline/SKILL.md"), "---\nname: shadowclone-baseline\n---\nManaged.\n");
    await Bun.write(path.join(source, ".agents/skills/notes/README.md"), "Not a skill.\n");
    await Bun.write(path.join(workspace, "AGENTS.md"), `Run tests in ${workspace}.\n`);
    await mkdir(home, { recursive: true });

    expect(await copyPersonalLibrary({ sourceHome: source, targetHome: home })).toEqual({ skills: 1 });
    const arm = await captureArm({ home, workspace, sourceHome: source });

    expect(arm.files.map((file) => `${file.root}/${file.path}`)).toEqual([
      "home/.agents/skills/names/rules.md",
      "home/.agents/skills/names/SKILL.md",
      "workspace/AGENTS.md",
    ]);
    expect(arm.files.find((file) => file.path.endsWith("SKILL.md"))?.content).toContain("{{home}}/.agents/skills/names/rules.md");
    expect(arm.files.find((file) => file.root === "workspace")?.content).toBe("Run tests in {{workspace}}.\n");
    expect(arm.fingerprint).toHaveLength(64);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("Claude capture reads Claude skills, instructions, and the shared repository files", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "study-claude-capture-"));

  try {
    const home = path.join(root, "home");
    const workspace = path.join(root, "workspace");
    await Bun.write(path.join(home, ".claude/skills/names/SKILL.md"), "---\nname: names\n---\nUse full words.\n");
    await Bun.write(path.join(home, ".claude/CLAUDE.md"), "Read the baseline.\n");
    await Bun.write(path.join(home, ".codex/AGENTS.md"), "Codex only.\n");
    await Bun.write(path.join(workspace, "AGENTS.md"), "Run tests.\n");
    await Bun.write(path.join(workspace, "CLAUDE.md"), "@AGENTS.md\n");
    await mkdir(home, { recursive: true });

    const claude = await captureArm({ home, workspace, sourceHome: root, engine: "claude-code" });
    const codex = await captureArm({ home, workspace, sourceHome: root });

    expect(claude.files.map((file) => `${file.root}/${file.path}`)).toEqual([
      "home/.claude/CLAUDE.md", "home/.claude/skills/names/SKILL.md", "workspace/AGENTS.md", "workspace/CLAUDE.md",
    ]);
    expect(codex.files.map((file) => `${file.root}/${file.path}`)).toEqual(["home/.codex/AGENTS.md", "workspace/AGENTS.md"]);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
