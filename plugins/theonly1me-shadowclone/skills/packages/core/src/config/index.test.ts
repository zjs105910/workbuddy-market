import { expect, test } from "bun:test";
import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import {
  defaultConfig,
  readConfig,
  renderConfig,
  sourceIds,
  writeConfig,
} from "./index";

test("defaults every capture source and deep distillation to off", () => {
  for (const sourceId of sourceIds) {
    expect(defaultConfig.sources[sourceId]).toBeFalse();
  }

  expect(defaultConfig.distillation.deep).toBeFalse();
});

test("reads a missing config as the disabled default", async () => {
  const directory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-config-"),
  );
  const configPath = path.join(directory, "missing.toml");

  expect(await readConfig({ configPath })).toEqual(defaultConfig);
});

test("writes and reads the config without changing it", async () => {
  const directory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-config-"),
  );
  const configPath = path.join(directory, "config.toml");

  const config = {
    ...defaultConfig,
    distillation: { ...defaultConfig.distillation, engine: "pi" as const, model: "custom/local-model" },
    sources: {
      ...defaultConfig.sources,
      "claude-code": true,
    },
  };

  await writeConfig({ config, configPath });

  expect(await readConfig({ configPath })).toEqual(config);
});

test("renders named source settings as TOML", () => {
  expect(renderConfig(defaultConfig)).toBe(
    [
      "schema-version = 1",
      "",
      "[sources]",
      "agent-context = false",
      "antigravity = false",
      "antigravity-workspaces = false",
      "claude-memory = false",
      "claude-rules = false",
      "claude-code = false",
      "claude-prompts = false",
      "codex = false",
      "cursor = false",
      "pi = false",
      "declared-rules = false",
      "git-metadata = false",
      "github-writing = false",
      "repository-manifests = false",
      "skill-library = false",
      "",
      "[distillation]",
      "deep = false",
      "automatic = false",
      "",
    ].join("\n"),
  );
});

test("migrates an existing config with git metadata disabled", async () => {
  const directory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-config-"),
  );
  const configPath = path.join(directory, "config.toml");
  const legacy = renderConfig(defaultConfig)
    .replace("agent-context = false\n", "")
    .replace("antigravity = false\n", "")
    .replace("declared-rules = false\n", "")
    .replace("pi = false\n", "")
    .replace("git-metadata = false\n", "")
    .replace("github-writing = false\n", "");

  await Bun.write(configPath, legacy);

  const migrated = await readConfig({ configPath });

  expect(migrated.sources["declared-rules"]).toBeFalse();
  expect(migrated.sources["claude-rules"]).toBeFalse();
  expect(migrated.sources["git-metadata"]).toBeFalse();
  expect(migrated.sources["github-writing"]).toBeFalse();
  expect(migrated.sources.pi).toBeFalse();
});

test("migrates an existing config with Antigravity disabled", async () => {
  const directory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-config-"),
  );
  const configPath = path.join(directory, "config.toml");
  const legacy = renderConfig(defaultConfig)
    .replace("agent-context = false\n", "")
    .replace("antigravity = false\n", "");

  await Bun.write(configPath, legacy);

  expect((await readConfig({ configPath })).sources.antigravity).toBeFalse();
});

test("migrates an existing config with agent context omitted", async () => {
  const directory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-config-"),
  );
  const configPath = path.join(directory, "config.toml");
  const legacy = renderConfig(defaultConfig).replace(
    "agent-context = false\n",
    "",
  );

  await Bun.write(configPath, legacy);

  expect(
    (await readConfig({ configPath })).sources["agent-context"],
  ).toBeFalse();
});

test("ignores a repository action table left by an earlier version", async () => {
  const directory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-config-"),
  );
  const configPath = path.join(directory, "config.toml");

  await Bun.write(configPath, `${renderConfig(defaultConfig)}
[repo."github.com/acme/platform"]
allow = ["push"]
maxBudgetUsd = 2
`);

  expect(await readConfig({ configPath })).toEqual(defaultConfig);
  expect(renderConfig(await readConfig({ configPath }))).not.toContain("maxBudgetUsd");
});

test("rejects unknown source names instead of silently enabling them", async () => {
  const directory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-config-"),
  );
  const configPath = path.join(directory, "config.toml");
  const text = renderConfig(defaultConfig).replace(
    "skill-library = false",
    "skill-library = false\nbrowser = true",
  );

  await Bun.write(configPath, text);

  await expect(readConfig({ configPath })).rejects.toThrow(
    "no unknown sources",
  );
});
