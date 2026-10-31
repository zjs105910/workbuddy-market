import { expect, test } from "bun:test";
import path from "node:path";
import { rm } from "node:fs/promises";
import { readConfig, writeConfig } from "@shadowclone/core";
import { resolveRepository } from "@shadowclone/sessions";
import { skillFixture } from "./testing";
import { learningRecord } from "./fixtures";
import { skillPublication } from "./publication";
import { readEnvironment, writeEnvironment } from "./store";
import { syncLearningEnvironment } from "./sync";
import { emptyEnvironment, type LearningRecord } from "./types";
import { renderSkillRouting } from "./context";
import { learningScopes } from "./scope";

const initialText = "---\nname: palette-check\ndescription: Check palettes\n---\n\n# Checks\n\nValidate every export.\n";

async function routingFixture(options: { readonly nearCapacity?: boolean } = {}) {
  const setup = await skillFixture({ scope: "repository" });
  const initialized = Bun.spawnSync(["git", "init", setup.cwd], { stdout: "ignore", stderr: "pipe" });
  expect(initialized.exitCode).toBe(0);
  const configured = Bun.spawnSync(["git", "-C", setup.cwd, "config", "remote.origin.url", "https://github.com/synthetic/palettes.git"]);
  expect(configured.exitCode).toBe(0);
  const resolved = await resolveRepository({ cwd: setup.cwd, enabled: true });
  if (!resolved.profileFileName) throw new Error("Expected a synthetic repository identity");

  const repository = { directory: setup.cwd, originDirectory: resolved.origin.directoryName, repositoryName: resolved.profileFileName };
  const scope = { key: `${repository.originDirectory}/${repository.repositoryName}`, directory: setup.cwd, repository };
  const sourceRecord = learningRecord();
  const record: LearningRecord = {
    ...sourceRecord,
    rule: { ...sourceRecord.rule, scope: "project", originDirectory: repository.originDirectory, repositoryName: repository.repositoryName },
  };
  const config = await readConfig({ configPath: setup.paths.configFile });
  await writeConfig({ configPath: setup.paths.configFile, config: {
    ...config, sources: { ...config.sources, "git-metadata": true },
  } });

  const publication = await skillPublication({
    paths: setup.paths,
    state: { ...emptyEnvironment, phase: "active", repositories: [repository], records: [record] },
    scope, skill: null, name: "palette-check", text: initialText, records: [record],
  });

  for (const update of publication.updates) {
    if (update.next !== null) await Bun.write(update.filePath, update.next);
  }

  await writeEnvironment({ paths: setup.paths, state: {
    ...publication.state,
    facts: options.nearCapacity
      ? Array.from({ length: 6 }, () => ({ scope: scope.key, text: "A synthetic scoped fact. ".repeat(21), learningKeys: [] }))
      : [],
  } });
  const instructions = path.join(setup.cwd, "AGENTS.md");
  await Bun.write(instructions, "Keep this manually authored instruction.\n");
  await syncLearningEnvironment(setup.paths);

  return { ...setup, instructions, target: path.join(setup.cwd, ".agents/skills/palette-check/SKILL.md") };
}

test("native routing follows description edits and repairs stale metadata without replacing manual sections", async () => {
  const setup = await routingFixture();

  try {
    const description = "Check palettes, exports, and accessibility";
    await Bun.write(setup.target, initialText.replace("description: Check palettes", `description: ${description}`));
    await syncLearningEnvironment(setup.paths);
    const current = await readEnvironment(setup.paths);
    if (!current) throw new Error("Expected the published state");

    expect(current.artifacts.filter(({ kind }) => kind === "skill").every((artifact) => artifact.description === description)).toBeTrue();
    expect(renderSkillRouting({ state: current, scopes: learningScopes({ paths: setup.paths, state: current }) })).toContain(description);
    expect(await Bun.file(setup.instructions).text()).toBe("Keep this manually authored instruction.\n");

    await writeEnvironment({ paths: setup.paths, state: {
      ...current,
      artifacts: current.artifacts.map((artifact) => artifact.kind === "skill" ? { ...artifact, description: "Check palettes" } : artifact),
    } });
    await syncLearningEnvironment(setup.paths);
    expect((await readEnvironment(setup.paths))?.artifacts.filter(({ kind }) => kind === "skill").every((artifact) => artifact.description === description)).toBeTrue();
    const instructions = await Bun.file(setup.instructions).text();
    await syncLearningEnvironment(setup.paths);
    expect(await Bun.file(setup.instructions).text()).toBe(instructions);
  } finally {
    await rm(setup.home, { recursive: true, force: true });
  }
});

test("routing overflow keeps the previous native section and queues a specific decision", async () => {
  const setup = await routingFixture({ nearCapacity: true });

  try {
    const before = await Bun.file(setup.instructions).text();
    const edited = initialText.replace("description: Check palettes", `description: ${"Check palettes and exports. ".repeat(35)}`);
    await Bun.write(setup.target, edited);
    await syncLearningEnvironment(setup.paths);

    const state = await readEnvironment(setup.paths);
    expect(state?.dispositions[0]?.status).toBe("pending");
    expect(state?.dispositions[0]?.reason).toContain("Native routing exceeds 4 KiB");
    expect(state?.artifacts.filter(({ kind }) => kind === "skill").every(({ description }) => description === "Check palettes")).toBeTrue();
    expect(await Bun.file(setup.instructions).text()).toBe(before);
    expect(await Bun.file(setup.target).text()).toBe(edited);
    expect(await Bun.file(path.join(setup.cwd, ".claude/skills/palette-check/SKILL.md")).text()).toBe(initialText);
  } finally {
    await rm(setup.home, { recursive: true, force: true });
  }
});
