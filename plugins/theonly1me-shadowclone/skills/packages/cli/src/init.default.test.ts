import { expect, test } from "bun:test";
import { mkdir, mkdtemp, symlink } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { readConfig, createProjectPaths } from "@shadowclone/core";
import { readMaintenanceState } from "@shadowclone/skills";
import { answerIsYes, initialize } from "./init";
import { readProfileSnapshot } from "@shadowclone/environment";
import { fixtureSkill } from "@shadowclone/skills/testing";

test("default yes prompt treats an explicit no as declined consent", () => {
  expect(answerIsYes("")).toBeTrue();
  expect(answerIsYes("Y")).toBeTrue();
  expect(answerIsYes("yes")).toBeTrue();
  expect(answerIsYes("n")).toBeFalse();
  expect(answerIsYes("no")).toBeFalse();
  expect(answerIsYes(null)).toBeFalse();
});

test("default setup asks three questions and enables only detected session sources", async () => {
  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-init-default-"),
  );
  const paths = createProjectPaths({ homeDirectory, platform: "darwin" });

  const questions: string[] = [];
  const output: string[] = [];
  const installs: string[] = [];

  await initialize({
    paths,
    workingDirectory: homeDirectory,
    presence: {
      hasRepositoryGuidance: false,
      presentCaptureSources: new Set(["claude-code", "codex"]),
    },
    agents: ["claude-code", "codex"],
    ask: (question) => {
      questions.push(question);

      return questions.length === 1;
    },
    install: async (options) => {
      installs.push(...options.agents);

      return { skipped: [] };
    },
    writeLine: (line) => output.push(line),
  });

  const config = await readConfig({ configPath: paths.configFile });

  expect(questions).toHaveLength(3);
  expect(
    questions.every((question) => !/eval|baseline/i.test(question)),
  ).toBeTrue();
  expect(config.sources["claude-code"]).toBeTrue();
  expect(config.sources.codex).toBeTrue();
  expect(config.sources.cursor).toBeFalse();
  expect("shell" in config.sources).toBeFalse();
  expect(config.sources["git-metadata"]).toBeTrue();
  expect(config.sources["agent-context"]).toBeTrue();
  expect(config.sources["skill-library"]).toBeFalse();
  expect(config.distillation.deep).toBeTrue();
  expect(config.distillation.automatic).toBeFalse();
  expect(installs).toEqual(["claude-code", "codex"]);
  expect(output.join("\n")).toContain("~/.claude/projects");
  expect(output.join("\n")).toContain("~/.codex/sessions");
  expect(output.join("\n")).not.toContain("~/.cursor/chats");
});

test("declining background learning makes no model call", async () => {
  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-init-default-"),
  );
  const paths = createProjectPaths({ homeDirectory, platform: "darwin" });
  let calls = 0;

  await initialize({
    paths,
    workingDirectory: homeDirectory,
    presence: {
      hasRepositoryGuidance: false,
      presentCaptureSources: new Set(),
    },
    agents: [],
    ask: () => false,
    runner: () => {
      calls += 1;

      throw new Error("The model must not run");
    },
    engine: "codex",
    writeLine: () => {},
  });

  const config = await readConfig({ configPath: paths.configFile });

  expect(calls).toBe(0);
  expect(config.distillation.deep).toBeFalse();
  expect(config.distillation.automatic).toBeFalse();
});

test("skill consent works without enabling transcript capture or model calls", async () => {
  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-init-default-"),
  );
  const paths = createProjectPaths({ homeDirectory, platform: "darwin" });

  await Bun.write(
    path.join(homeDirectory, ".claude/skills/typed-changes/SKILL.md"),
    fixtureSkill(),
  );

  let modelCalls = 0;

  await initialize({
    paths,
    workingDirectory: homeDirectory,
    presence: {
      hasRepositoryGuidance: false,
      presentCaptureSources: new Set(),
    },
    agents: [],
    ask: (question) => question.startsWith("Keep your skills"),
    runner: () => {
      modelCalls += 1;

      throw new Error("The model must not run");
    },
    engine: "codex",
    managedConfigPath: null,
    writeLine: () => {},
  });

  const config = await readConfig({ configPath: paths.configFile });

  expect(config.sources["skill-library"]).toBeTrue();
  expect(config.sources["claude-code"]).toBeFalse();
  expect(config.distillation.deep).toBeFalse();
  expect(config.distillation.automatic).toBeFalse();
  expect((await readMaintenanceState(paths)).roots.length).toBeGreaterThan(0);
  expect(
    await Bun.file(
      path.join(homeDirectory, ".agents/skills/typed-changes/SKILL.md"),
    ).text(),
  ).toBe(fixtureSkill());
  expect(
    await Bun.file(
      path.join(homeDirectory, ".codex/skills/typed-changes/SKILL.md"),
    ).exists(),
  ).toBeFalse();
  expect(modelCalls).toBe(0);
});

test("default setup retains imported guidance as internal learning with an injected clock and runner", async () => {
  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-init-default-"),
  );
  const paths = createProjectPaths({ homeDirectory, platform: "darwin" });

  await Bun.write(
    path.join(homeDirectory, "CLAUDE.md"),
    "# Plan the smallest change\n",
  );

  const linkedSkill = path.join(homeDirectory, ".claude", "skills", "linked");

  await mkdir(path.dirname(linkedSkill), { recursive: true });
  await symlink(
    await mkdtemp(path.join(os.tmpdir(), "shadowclone-external-skill-")),
    linkedSkill,
  );
  await initialize({
    paths,
    workingDirectory: homeDirectory,
    presence: { hasRepositoryGuidance: true, presentCaptureSources: new Set() },
    agents: [],
    ask: (question) => !question.startsWith("Keep your skills"),
    runner: () => {
      throw new Error("No sessions were detected");
    },
    engine: "codex",
    now: 1_800_000_000_000,
    managedConfigPath: null,
    writeLine: () => {},
  });

  expect((await readProfileSnapshot(paths)).rules).toHaveLength(1);
  expect(await Bun.file(paths.profileManifestFile).exists()).toBeFalse();
});

test("setup reports an agent it skipped and counts only the agents it installed", async () => {
  const homeDirectory = await mkdtemp(path.join(os.tmpdir(), "shadowclone-init-skipped-"));
  const paths = createProjectPaths({ homeDirectory, platform: "darwin" });
  const output: string[] = [];

  await initialize({
    paths,
    workingDirectory: homeDirectory,
    presence: {
      hasRepositoryGuidance: false,
      presentCaptureSources: new Set(["claude-code", "codex"]),
    },
    agents: ["claude-code", "codex"],
    ask: (_question) => false,
    install: async () => ({
      skipped: [
        { agent: "codex", kind: "link", path: "/home/sample/.codex/AGENTS.md", target: "/home/sample/.agents/AGENTS.md" },
      ],
    }),
    writeLine: (line) => output.push(line),
  });

  const lines = output.join("\n");

  expect(lines).toContain("1 agents installed.");
  expect(output.at(-1)).toBe(
    "Not installed for codex: /home/sample/.codex/AGENTS.md is a symbolic link to /home/sample/.agents/AGENTS.md. Shadowclone does not write through links, so codex gets no Shadowclone guidance. Replace the link with a regular file, then run shadowclone install --agent codex.",
  );
});
