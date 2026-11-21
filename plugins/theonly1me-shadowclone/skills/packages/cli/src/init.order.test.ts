import { expect, test } from "bun:test";
import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { createProjectPaths } from "@shadowclone/core";
import { loadSeedLibrary } from "@shadowclone/skills";
import { initialize } from "./init";

test("completes the wizard before filtered source consent", async () => {
  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-onboarding-"),
  );
  const paths = createProjectPaths({ homeDirectory, platform: "darwin" });
  const library = await loadSeedLibrary();

  const events: string[] = [];
  const output: string[] = [];
  const answers = ["1", "1", "1", "1", "1", "none"];

  await initialize({
    advanced: true,
    paths,
    configPath: paths.configFile,
    workingDirectory: homeDirectory,
    presence: {
      hasRepositoryGuidance: false,
      presentCaptureSources: new Set(["claude-code"]),
    },
    library,
    answer: () => {
      events.push("wizard answer");

      return answers.shift() ?? null;
    },
    ask: (question) => {
      events.push(question);

      return (
        question === "Write these rules to your profile?" ||
        question === "Enable Claude Code transcripts?"
      );
    },
    writeLine: (line) => output.push(line),
  });

  expect(events[0]).toBe("wizard answer");
  expect(events).toContain("Enable Claude Code transcripts?");
  expect(events).not.toContain("Enable Antigravity CLI transcripts?");
  expect(events.indexOf("Enable Claude Code transcripts?")).toBeGreaterThan(
    events.indexOf("Write these rules to your profile?"),
  );
  expect(output.at(-1)).toBe(
    "Run shadowclone learn to build evidence from the sources you enabled.",
  );
});
