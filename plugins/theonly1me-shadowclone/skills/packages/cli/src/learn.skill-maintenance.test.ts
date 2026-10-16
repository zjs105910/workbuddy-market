import { expect, test } from "bun:test";
import type { EngineRunner } from "@shadowclone/agents";
import { skillEngineRun, skillFixture } from "@shadowclone/environment/testing";
import { learn } from "./learn";

test("deep learn reports deferred skill assessments", async () => {
  const setup = await skillFixture();
  const lines: string[] = [];
  const runner: EngineRunner = () =>
    Promise.resolve({
      ...skillEngineRun(null),
      costUsd: null,
      isError: true,
      errorMessage: "Maximum budget reached",
    });

  await learn({
    paths: setup.paths,
    configPath: setup.configPath,
    databasePath: setup.paths.indexDatabase,
    managedConfigPath: null,
    deep: true,
    apply: true,
    engine: "claude-code",
    runner,
    writeLine: (line) => {
      lines.push(line);
    },
  });

  expect(lines).toContain(
    "Skill maintenance: 0 synced, 0 updated, 0 pending, 1 deferred, 0 conflicts.",
  );
});
