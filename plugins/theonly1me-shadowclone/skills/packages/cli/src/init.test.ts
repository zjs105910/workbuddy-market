import { expect, test } from "bun:test";
import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { readConfig, createProjectPaths } from "@shadowclone/core";
import { type ConsentPrompt, initialize } from "./init";
import { onboardingCaptureSourceIds } from "./onboardingPresence";

async function initializeWithAllSources(options: {
  readonly configPath: string;
  readonly ask: ConsentPrompt;
  readonly writeLine?: (line: string) => void;
}): Promise<void> {
  const paths = createProjectPaths({
    homeDirectory: path.dirname(options.configPath),
    platform: "darwin",
  });

  await initialize({
    ...options,
    paths,
    advanced: true,
    ask: (question) =>
      question === "Enable Pi transcripts?" ||
      question === "Import existing repository guidance?" ||
      question === "Set up a seed profile instead?"
        ? false
        : options.ask(question),
    writeLine: options.writeLine ?? (() => {}),
    presence: {
      hasRepositoryGuidance: true,
      presentCaptureSources: new Set(onboardingCaptureSourceIds),
    },
  });
}

test("enables Claude Code only after consent", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "shadowclone-init-"));
  const configPath = path.join(directory, "config.toml");
  const answers = [
    false,
    true,
    false,
    false,
    false,
    false,
    false,
    false,
  ];

  await initializeWithAllSources({
    configPath,
    ask: () => answers.shift() ?? false,
  });

  const config = await readConfig({ configPath });

  expect(config.sources.antigravity).toBeFalse();
  expect(config.sources["claude-code"]).toBeTrue();
  expect(config.sources["claude-prompts"]).toBeFalse();
  expect(config.sources.codex).toBeFalse();
  expect(config.sources.cursor).toBeFalse();
  expect(config.sources["git-metadata"]).toBeFalse();
  expect(config.sources["agent-context"]).toBeFalse();
  expect("shell" in config.sources).toBeFalse();
  expect(config.distillation.deep).toBeFalse();
});

test("enables git metadata only after separate consent", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "shadowclone-init-"));
  const configPath = path.join(directory, "config.toml");
  const answers = [
    false,
    false,
    false,
    false,
    false,
    true,
    false,
    false,
  ];

  await initializeWithAllSources({
    configPath,
    ask: () => answers.shift() ?? false,
  });

  const config = await readConfig({ configPath });

  expect(config.sources["claude-code"]).toBeFalse();
  expect(config.sources["git-metadata"]).toBeTrue();
  expect(config.sources["agent-context"]).toBeFalse();
});

test("enables agent context only after separate consent", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "shadowclone-init-"));
  const configPath = path.join(directory, "config.toml");
  const answers = [
    false,
    false,
    false,
    false,
    false,
    false,
    true,
    false,
  ];

  await initializeWithAllSources({
    configPath,
    ask: () => answers.shift() ?? false,
  });

  const config = await readConfig({ configPath });

  expect(config.sources["agent-context"]).toBeTrue();
  expect(config.sources["git-metadata"]).toBeFalse();
});

test("enables deep distillation only after separate consent", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "shadowclone-init-"));
  const configPath = path.join(directory, "config.toml");
  const answers = [
    false,
    false,
    false,
    false,
    false,
    false,
    false,
    false,
    false,
    true,
    false,
  ];

  await initializeWithAllSources({
    configPath,
    ask: () => answers.shift() ?? false,
  });

  const config = await readConfig({ configPath });

  expect(config.distillation.deep).toBeTrue();
  expect(Object.values(config.sources).every((enabled) => !enabled)).toBeTrue();
});

test("enables provider transcripts only after named consent", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "shadowclone-init-"));
  const configPath = path.join(directory, "config.toml");
  const questions: string[] = [];
  const answers = [true, false, false, true, true, false, false, false];

  await initializeWithAllSources({
    configPath,
    ask: (question) => {
      questions.push(question);

      return answers.shift() ?? false;
    },
  });

  const config = await readConfig({ configPath });

  expect(config.sources.antigravity).toBeTrue();
  expect(config.sources.codex).toBeTrue();
  expect(config.sources.cursor).toBeTrue();
  expect(questions).toContain("Enable Antigravity CLI transcripts?");
  expect(questions).toContain("Enable Codex transcripts?");
  expect(questions).toContain("Enable Cursor CLI chat stores?");
});

test("keeps every source off when consent is declined", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "shadowclone-init-"));
  const configPath = path.join(directory, "config.toml");

  const output: string[] = [];

  await initializeWithAllSources({
    configPath,
    ask: () => false,
    writeLine: (line) => output.push(line),
  });

  const config = await readConfig({ configPath });

  expect(Object.values(config.sources).every((enabled) => !enabled)).toBeTrue();
  expect(output[0]).toBe(
    "Existing agent instructions detected and left unread.",
  );
  expect(output).not.toContain(
    "Run shadowclone learn to build evidence from the sources you enabled.",
  );
});
