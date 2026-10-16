import { expect, test } from "bun:test";
import path from "node:path";
import { mkdir, symlink } from "node:fs/promises";
import { skillFixture, skillEngineRun } from "@shadowclone/environment/testing";
import { readConfig, writeConfig } from "@shadowclone/core";
import { createLearningExecution } from "@shadowclone/agents";
import { normalizeRemoteRepository } from "@shadowclone/sessions";
import { claudeMemoryDirectory } from "@shadowclone/profile";
import { emptyEnvironment, readEnvironment, writeEnvironment } from "@shadowclone/environment";
import { extractMemoryRecords } from "./memory";
import { updateLearningEnvironment } from "./update";

test("recurring memory is consented, redacted before the real planner, idempotent, and never modified", async () => {
  const setup = await skillFixture();
  const identity = normalizeRemoteRepository(
    "https://github.com/synthetic/repository.git",
  );

  if (!identity?.profileFileName) {
    throw new Error("Expected repository identity");
  }

  const repository = {
    directory: setup.cwd,
    originDirectory: identity.origin.directoryName,
    repositoryName: identity.profileFileName,
  };
  const state = {
    ...emptyEnvironment,
    automatic: true,
    repositories: [repository],
  };
  const directory = claudeMemoryDirectory({
    paths: setup.paths,
    repositoryRoot: setup.cwd,
  });
  const filePath = path.join(directory, "feedback_process.md");
  const secret = `ghp_${"a".repeat(36)}`;
  const original = `---\nname: Workflow\ntype: feedback\n---\nCheck preconditions. Credential ${secret}\n`;

  await Bun.write(filePath, original);

  expect(
    await extractMemoryRecords({ paths: setup.paths, state, enabled: false }),
  ).toEqual(state);

  const extracted = await extractMemoryRecords({
    paths: setup.paths,
    state,
    enabled: true,
  });

  expect(extracted.records[0]?.rule.body).not.toContain(secret);

  await writeEnvironment({ paths: setup.paths, state });

  const config = await readConfig({ configPath: setup.paths.configFile });

  await writeConfig({
    configPath: setup.paths.configFile,
    config: {
      ...config,
      sources: {
        ...config.sources,
        "claude-memory": true,
        "git-metadata": true,
      },
    },
  });

  let calls = 0;

  const execution = createLearningExecution({
    engine: "claude-code",
    runner: async (run) => {
      calls += 1;

      expect(run.prompt).not.toContain(secret);
      expect(run.prompt).toContain("Check preconditions");

      const record = (await readEnvironment(setup.paths))?.records[0];

      if (!record) {
        throw new Error("Expected memory learning");
      }

      return skillEngineRun({
        routes: [
          {
            key: record.rule.key,
            destination: "pending",
            skillId: "",
            name: "",
            description: "",
            reason: "Needs technical verification",
          },
        ],
      });
    },
  });

  await updateLearningEnvironment({
    ...setup,
    execution,
    readRemote: async () => "https://github.com/synthetic/repository.git",
  });

  expect(calls).toBe(1);

  await updateLearningEnvironment({
    ...setup,
    execution,
    readRemote: async () => "https://github.com/synthetic/repository.git",
  });

  expect(calls).toBe(1);
  expect(await Bun.file(filePath).text()).toBe(original);
});

test("memory extraction rejects linked repository memory roots", async () => {
  const setup = await skillFixture();
  const directory = claudeMemoryDirectory({
    paths: setup.paths,
    repositoryRoot: setup.cwd,
  });
  const target = path.join(setup.home, "external-memory");

  await mkdir(target);
  await mkdir(path.dirname(directory), { recursive: true });
  await symlink(target, directory);

  await expect(
    extractMemoryRecords({
      paths: setup.paths,
      state: {
        ...emptyEnvironment,
        repositories: [
          {
            directory: setup.cwd,
            originDirectory: "synthetic",
            repositoryName: "repository",
          },
        ],
      },
      enabled: true,
    }),
  ).rejects.toThrow("symbolic links");
});
