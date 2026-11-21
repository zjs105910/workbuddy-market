import { expect, test } from "bun:test";
import path from "node:path";
import { mkdir } from "node:fs/promises";
import { bunTaskList, harnessTestSetup } from "@shadowclone/harness/testing";
import { claudeMemoryDirectory } from "@shadowclone/profile";
import { harnessInitCommand, parseRepositoryInit } from "./harness";
import { harnessSyncCommand } from "./harnessSync";

test("init --repo flags default to enforcing in Claude and asking about personal rules", () => {
  expect(parseRepositoryInit([])).toEqual({
    personal: null,
    skills: [],
    enforceClaude: true,
  });
  expect(
    parseRepositoryInit([
      "--no-personal",
      "--skill",
      "clean-code",
      "--no-enforce",
    ]),
  ).toEqual({ personal: false, skills: ["clean-code"], enforceClaude: false });
  expect(parseRepositoryInit(["--apply"])).toBeNull();
});

test("init --repo previews first and writes nothing unless the owner confirms", async () => {
  const setup = await harnessTestSetup({ fixture: bunTaskList });
  const run = (answer: boolean) =>
    harnessInitCommand({
      apply: "confirm",
      personal: false,
      skills: [],
      enforceClaude: true,
      cwd: setup.root,
      paths: setup.paths,
      managedConfigPath: null,
      ask: () => answer,
      writeLine: () => undefined,
    });

  expect(await run(false)).toBeNull();
  expect(
    await Bun.file(path.join(setup.root, "AGENTS.md")).exists(),
  ).toBeFalse();
  expect(await run(true)).not.toBeNull();
  expect(
    await Bun.file(path.join(setup.root, "AGENTS.md")).exists(),
  ).toBeTrue();
  expect(
    await Bun.file(path.join(setup.root, ".claude/settings.local.json")).text(),
  ).toContain("shadowclone check --changed --format claude-stop");
});

test("sync leaves a repository without Shadowclone files alone", async () => {
  const setup = await harnessTestSetup({ fixture: bunTaskList });

  expect(
    await harnessSyncCommand({
      apply: "confirm",
      cwd: setup.root,
      paths: setup.paths,
      managedConfigPath: null,
      ask: () => {
        throw new Error("asked");
      },
      writeLine: () => undefined,
    }),
  ).toBeNull();
  expect(
    await Bun.file(path.join(setup.root, "AGENTS.md")).exists(),
  ).toBeFalse();
});

test("sync offers consented memory notes without creating a repository harness", async () => {
  const setup = await harnessTestSetup({
    fixture: bunTaskList,
    sources: { "claude-memory": true },
  });
  const directory = claudeMemoryDirectory({
    paths: setup.paths,
    repositoryRoot: setup.root,
  });

  await mkdir(directory, { recursive: true });
  await Bun.write(
    path.join(directory, "feedback_review.md"),
    "---\nname: review\ndescription: Keep reviews short\n---\nUse short reviews.\n",
  );

  const lines: string[] = [];

  await harnessSyncCommand({
    apply: false,
    cwd: setup.root,
    paths: setup.paths,
    managedConfigPath: null,
    ask: () => {
      throw new Error("asked");
    },
    writeLine: (line) => lines.push(line),
  });

  expect(lines.join("\n")).toContain("1 Claude memory note");

  const prompts: string[] = [];

  expect(
    await harnessSyncCommand({
      apply: "confirm",
      cwd: setup.root,
      paths: setup.paths,
      managedConfigPath: null,
      ask: (prompt) => {
        prompts.push(prompt);

        return false;
      },
      writeLine: () => undefined,
    }),
  ).toBeNull();
  expect(prompts).toHaveLength(1);
  expect(
    await Bun.file(path.join(setup.root, "AGENTS.md")).exists(),
  ).toBeFalse();
});
