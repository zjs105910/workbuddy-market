import { expect, test } from "bun:test";
import { mkdir, symlink } from "node:fs/promises";
import path from "node:path";
import { defaultConfig, writeConfig } from "@shadowclone/core";
import { readClaudeRules } from "./claudeRules";
import { compileContextDetails } from "./compile";
import { integrationFixture } from "@shadowclone/core/testing";

test("session context omits a rule the repository instructions state only with repository guidance consent", async () => {
  const fixture = await integrationFixture();

  await Bun.write(
    path.join(fixture.paths.profileDirectory, "global/workflow.md"),
    "## Gate\n\nRun the full check script before presenting any change.\n",
  );
  await Bun.write(
    path.join(fixture.cwd, "CLAUDE.md"),
    "# Repository\n\nRun the full check script before presenting any change.\n",
  );

  const compile = () =>
    compileContextDetails({
      ...fixture,
      format: "index",
      nativeDuplicates: "including-harness",
    });

  expect((await compile())?.compilation.markdown).toContain(
    "Run the full check script",
  );

  await writeConfig({
    configPath: fixture.paths.configFile,
    config: {
      ...defaultConfig,
      sources: { ...defaultConfig.sources, "declared-rules": true },
    },
  });

  const deduplicated = await compile();

  expect(deduplicated?.compilation.markdown).not.toContain(
    "Run the full check script",
  );
  expect(deduplicated?.compilation.markdown).toContain(
    "- Naming: Use complete names.",
  );
  expect(
    deduplicated?.compilation.omissions.map((omission) => omission.reason),
  ).toContain("known-duplicate");
});

test("Claude rule duplicate detection requires its own consent and redacts source text", async () => {
  const fixture = await integrationFixture();
  const ruleDirectory = path.join(fixture.cwd, ".claude/rules/nested");

  await mkdir(ruleDirectory, { recursive: true });
  await Bun.write(
    path.join(fixture.paths.profileDirectory, "global/workflow.md"),
    "## Gate\n\nRun the full check script before presenting any change.\n",
  );
  await Bun.write(
    path.join(ruleDirectory, "gate.md"),
    ("Run the full check script before presenting any change.\nOPENAI_API_KEY=" + ["sk", "proj", "abc123DEF456ghi789JKL"].join("-") + "\n"),
  );

  const compile = () =>
    compileContextDetails({
      ...fixture,
      format: "index",
      nativeDuplicates: "including-harness",
    });

  expect((await compile())?.compilation.markdown).toContain(
    "Run the full check script",
  );

  await writeConfig({
    configPath: fixture.paths.configFile,
    config: {
      ...defaultConfig,
      sources: { ...defaultConfig.sources, "claude-rules": true },
    },
  });

  const deduplicated = await compile();

  expect(deduplicated?.compilation.markdown).not.toContain(
    "Run the full check script",
  );
  expect(
    deduplicated?.compilation.omissions.map((omission) => omission.reason),
  ).toContain("known-duplicate");
  expect((await readClaudeRules(fixture.cwd)).join("\n")).not.toContain(
    ["sk", "proj", "abc123DEF456ghi789JKL"].join("-"),
  );
});

test("Claude rule duplicate detection rejects a linked .claude parent", async () => {
  const fixture = await integrationFixture();
  const linkedParent = path.join(fixture.home, "linked-claude");

  await mkdir(path.join(linkedParent, "rules"), { recursive: true });
  await Bun.write(
    path.join(linkedParent, "rules/gate.md"),
    "Run the full check script.\n",
  );
  await symlink(linkedParent, path.join(fixture.cwd, ".claude"), "dir");

  await expect(readClaudeRules(fixture.cwd)).rejects.toThrow("symbolic link");
});
