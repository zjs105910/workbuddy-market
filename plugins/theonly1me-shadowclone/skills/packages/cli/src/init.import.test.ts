import { expect, test } from "bun:test";
import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { createProjectPaths, readConfig, defaultManagedPolicy } from "@shadowclone/core";
import { initialize } from "./init";
import { readProfileSnapshot } from "@shadowclone/environment";

test("offers to import detected repository guidance", async () => {
  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-init-import-"),
  );
  const paths = createProjectPaths({ homeDirectory, platform: "darwin" });
  const questions: string[] = [];

  await initialize({
    advanced: true,
    paths,
    configPath: paths.configFile,
    workingDirectory: homeDirectory,
    presence: {
      hasRepositoryGuidance: true,
      presentCaptureSources: new Set(),
    },
    ask: (question) => {
      questions.push(question);

      return false;
    },
    writeLine: () => {},
  });

  expect(questions[0]).toBe("Import existing repository guidance?");
  expect(questions[1]).toBe("Set up a seed profile instead?");
});

test("imports accepted guidance after configuration and skips seed selection", async () => {
  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-init-import-"),
  );
  const paths = createProjectPaths({ homeDirectory, platform: "darwin" });

  await Bun.write(path.join(homeDirectory, "CLAUDE.md"), "# Plan first");

  await initialize({
    advanced: true,
    paths,
    configPath: paths.configFile,
    workingDirectory: homeDirectory,
    managedConfigPath: null,
    presence: {
      hasRepositoryGuidance: true,
      presentCaptureSources: new Set(),
    },
    answer: () => {
      throw new Error("Seed wizard must not run after import acceptance");
    },
    ask: (question) => question === "Import existing repository guidance?",
    writeLine: () => {},
  });

  const config = await readConfig({ configPath: paths.configFile });
  const state = (await readProfileSnapshot(paths)).rules.map(
    ({ rule }) => rule,
  );

  expect(config.sources["declared-rules"]).toBeTrue();
  expect(state).toHaveLength(1);
});

test("offers seed guidance when managed policy blocks import", async () => {
  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-init-import-"),
  );
  const paths = createProjectPaths({ homeDirectory, platform: "darwin" });
  const questions: string[] = [];
  const output: string[] = [];

  await initialize({
    advanced: true,
    paths,
    configPath: paths.configFile,
    workingDirectory: homeDirectory,
    presence: {
      hasRepositoryGuidance: true,
      presentCaptureSources: new Set(),
    },
    managedPolicy: {
      ...defaultManagedPolicy,
      allowedSources: defaultManagedPolicy.allowedSources.filter(
        (source) => source !== "declared-rules",
      ),
    },
    ask: (question) => {
      questions.push(question);

      return false;
    },
    writeLine: (line) => output.push(line),
  });

  expect(questions[0]).toBe("Set up a seed profile instead?");
  expect(questions).not.toContain("Import existing repository guidance?");
  expect(output[0]).toBe("Managed policy blocks repository guidance import.");
});
