import { expect, test } from "bun:test";
import { skillFixture } from "./testing";
import { readEnvironment, environmentFile } from "./store";
import { prepareEnvironmentMigration } from "./migrate";
import { reviewLearning } from "./controls";
import { activateEnvironment } from "./activate";
import { undoRevision } from "./undo";

test("migration preview is read-only, activation requires coverage, and activation can be undone", async () => {
  const setup = await skillFixture();

  const preview = await prepareEnvironmentMigration({
    paths: setup.paths,
    repositories: [],
    automatic: true,
    apply: false,
  });

  expect(preview.records.length).toBeGreaterThan(0);
  expect(await Bun.file(environmentFile(setup.paths)).exists()).toBeFalse();

  const prepared = await prepareEnvironmentMigration({
    paths: setup.paths,
    repositories: [],
    automatic: true,
    apply: true,
  });

  expect(prepared.phase).toBe("preparing");
  expect(prepared.baselineDirectory).not.toBeNull();
  await expect(activateEnvironment(setup.paths)).rejects.toThrow(
    "still need publication",
  );

  for (const record of prepared.records) {
    await reviewLearning({
      paths: setup.paths,
      key: record.rule.key,
      action: "exclude",
      reason: "Explicit synthetic test decision",
    });
  }

  const revision = await activateEnvironment(setup.paths);

  expect((await readEnvironment(setup.paths))?.phase).toBe("active");

  if (!revision) {
    throw new Error("Expected activation revision");
  }

  await undoRevision({ paths: setup.paths, id: revision });

  expect((await readEnvironment(setup.paths))?.phase).toBe("preparing");

  const resumed = await prepareEnvironmentMigration({
    paths: setup.paths,
    repositories: [],
    automatic: true,
    apply: true,
  });

  expect(resumed.baselineDirectory).toBe(prepared.baselineDirectory);
});

test("activation preserves a skill edited after publication", async () => {
  const setup = await skillFixture();

  const prepared = await prepareEnvironmentMigration({
    paths: setup.paths,
    repositories: [],
    automatic: true,
    apply: true,
  });

  for (const record of prepared.records) {
    await reviewLearning({
      paths: setup.paths,
      key: record.rule.key,
      action: "exclude",
      reason: "Explicit synthetic test decision",
    });
  }

  const baseline = prepared.artifacts.find(
    (artifact) => artifact.name === "shadowclone-baseline",
  );

  if (!baseline) {
    throw new Error("Expected baseline");
  }

  const changed = `${await Bun.file(baseline.filePath).text()}\nA manual edit.\n`;

  await Bun.write(baseline.filePath, changed);

  await expect(activateEnvironment(setup.paths)).rejects.toThrow(
    "changed before activation",
  );
  expect(await Bun.file(baseline.filePath).text()).toBe(changed);
  expect((await readEnvironment(setup.paths))?.phase).toBe("preparing");
});
