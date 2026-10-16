import { expect, test } from "bun:test";
import path from "node:path";
import { harnessInitCommand } from "../harness";
import { harnessSyncCommand } from "../harnessSync";
import {
  compileContextDetails,
  sessionStartProjection,
  writeProfile,
} from "@shadowclone/environment";
import { claudeMemoryDirectory } from "@shadowclone/profile";
import type { ProfileRule } from "@shadowclone/profile";
import {
  acceptAll,
  bunTaskList,
  harnessTestSetup,
  type HarnessTestSetup,
} from "@shadowclone/harness/testing";

function note(options: {
  readonly name: string;
  readonly description: string;
  readonly type: string;
  readonly body: string;
}): string {
  return [
    "---",
    `name: ${options.name}`,
    `description: ${options.description}`,
    "metadata:",
    `  type: ${options.type}`,
    "---",
    "",
    options.body,
    "",
  ].join("\n");
}

function init(setup: HarnessTestSetup) {
  return harnessInitCommand({
    apply: true,
    personal: true,
    skills: [],
    enforceClaude: false,
    cwd: setup.root,
    paths: setup.paths,
    managedConfigPath: null,
    ask: acceptAll,
    writeLine: () => undefined,
  });
}

test("sync turns only confirmed feedback and user notes into harness rules and never asks twice", async () => {
  const setup = await harnessTestSetup({
    fixture: bunTaskList,
    sources: { "claude-memory": true },
  });

  await init(setup);

  const memory = claudeMemoryDirectory({
    paths: setup.paths,
    repositoryRoot: setup.root,
  });

  await Bun.write(
    path.join(memory, "feedback_database.md"),
    note({
      name: "feedback_database",
      description: "Integration tests use a real database",
      type: "feedback",
      body: "Integration tests must hit a real database, never mocks.",
    }),
  );
  await Bun.write(
    path.join(memory, "project_deadline.md"),
    note({
      name: "project_deadline",
      description: "Release freeze on Friday",
      type: "project",
      body: "Freeze merges on Friday.",
    }),
  );
  await Bun.write(
    path.join(memory, "user_reviews.md"),
    note({
      name: "user_reviews",
      description: "Prefers small pull requests",
      type: "user",
      body: "Keep pull requests small.",
    }),
  );

  const answers = [true, false];
  const questions: string[] = [];

  await harnessSyncCommand({
    apply: true,
    cwd: setup.root,
    paths: setup.paths,
    managedConfigPath: null,
    writeLine: () => undefined,
    ask: (question) => {
      questions.push(question);

      return answers.shift() ?? false;
    },
  });

  expect(questions).toHaveLength(2);

  const agents = await Bun.file(path.join(setup.root, "AGENTS.md")).text();

  expect(agents).toContain(
    "- Integration tests use a real database: Integration tests must hit a real database, never mocks.",
  );
  expect(agents).not.toContain("small pull requests");
  expect(agents).not.toContain("Release freeze");

  await harnessSyncCommand({
    apply: true,
    cwd: setup.root,
    paths: setup.paths,
    managedConfigPath: null,
    writeLine: () => undefined,
    ask: () => {
      throw new Error("asked again");
    },
  });

  expect(await Bun.file(path.join(setup.root, "AGENTS.md")).text()).toBe(
    agents,
  );
});

test("session-start context leaves out rules the committed harness already carries", async () => {
  const setup = await harnessTestSetup({ fixture: bunTaskList });
  const rule: ProfileRule = {
    key: "declared-small-files",
    title: "Small files",
    body: "Keep every file under 200 lines.",
    section: "engineering",
    scope: "global",
    originDirectory: null,
    repositoryName: null,
    source: "declared",
    status: "active",
    proposal: null,
    appliesWhen: [],
    evidence: { for: [], against: [] },
    observations: 0,
    lastSeen: "2026-09-26",
    sessions: 0,
    origins: [],
    importReference: null,
  };

  await writeProfile({ paths: setup.paths, rules: [rule] });
  await init(setup);

  const cwd = path.join(setup.root, "src");
  const startup = await compileContextDetails({
    paths: setup.paths,
    cwd,
    managedConfigPath: null,
    ...sessionStartProjection,
  });

  expect(startup?.compilation.markdown).not.toContain("Small files");
  expect(startup?.compilation.omissions).toContainEqual({
    ruleKey: "declared-small-files",
    reason: "in-harness",
  });

  const full = await compileContextDetails({
    paths: setup.paths,
    cwd,
    managedConfigPath: null,
    format: "index",
  });

  expect(full?.compilation.markdown).toContain(
    "- Small files: Keep every file under 200 lines.",
  );
});
