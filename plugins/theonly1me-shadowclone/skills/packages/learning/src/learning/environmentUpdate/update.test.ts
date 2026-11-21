import { expect, test } from "bun:test";
import path from "node:path";
import { createLearningExecution } from "@shadowclone/agents";
import { fingerprint } from "@shadowclone/core";
import { listRevisions } from "@shadowclone/changes";
import { learningRecord, skillEngineRun, skillFixture } from "@shadowclone/environment/testing";
import {
  emptyEnvironment,
  readEnvironment,
  readProfileSnapshot,
  undoRevision,
  writeEnvironment,
  writeProfile,
} from "@shadowclone/environment";
import { updateLearningEnvironment } from "./update";

const updatedDescription = "Make typed code changes and validate sample palettes.";

async function setupLearning() {
  const setup = await skillFixture();
  const record = learningRecord();

  await writeEnvironment({
    paths: setup.paths,
    state: { ...emptyEnvironment, automatic: true, records: [record] },
  });

  let calls = 0;

  const execution = createLearningExecution({
    engine: "claude-code",
    runner: async (run) => {
      calls += 1;

      expect(run.allowedTools).toEqual([]);

      if (run.prompt.includes("Organize durable")) {
        return skillEngineRun({
          routes: [
            {
              key: record.rule.key,
              destination: "skill",
              skillId: fingerprint(setup.filePath),
              name: "typed-changes",
              description: "Use for typed changes",
              reason: "Applies to this workflow",
            },
          ],
        });
      }

      return skillEngineRun({
        outcomes: [{ key: record.rule.key, disposition: "apply", reason: "Supported" }],
        description: updatedDescription,
        body: "",
        edits: [
          {
            before: "Preserve the requested behavior.",
            after: `Preserve the requested behavior. ${record.rule.body}`,
            keys: [record.rule.key],
          },
        ],
      });
    },
  });

  return { ...setup, record, execution, calls: () => calls };
}

test("learning maintains a skill, publishes portable copies, and skips unchanged evidence", async () => {
  const setup = await setupLearning();
  const first = await updateLearningEnvironment(setup);

  expect(first?.applied).toBe(1);
  expect(await Bun.file(setup.filePath).text()).toContain(
    setup.record.rule.body,
  );
  expect(
    await Bun.file(
      path.join(setup.home, ".agents/skills/typed-changes/SKILL.md"),
    ).text(),
  ).toBe(await Bun.file(setup.filePath).text());
  expect((await readEnvironment(setup.paths))?.dispositions[0]?.status).toBe(
    "published",
  );
  expect((await readEnvironment(setup.paths))?.artifacts.filter(({ kind }) => kind === "skill")
    .every(({ description }) => description === updatedDescription)).toBeTrue();

  await updateLearningEnvironment(setup);

  expect(setup.calls()).toBe(2);
  expect(await Bun.file(setup.paths.compiledProfileFile).exists()).toBeFalse();
});

test("undo restores every skill copy and its publication record", async () => {
  const setup = await setupLearning();

  await updateLearningEnvironment(setup);

  const revision = (await listRevisions(setup.paths)).find(
    ({ files }) => files > 1,
  );

  if (!revision) {
    throw new Error("Expected a publication revision");
  }

  await undoRevision({ paths: setup.paths, id: revision.id });

  expect(await Bun.file(setup.filePath).text()).toBe(setup.original);
  expect(
    await Bun.file(
      path.join(setup.home, ".agents/skills/typed-changes/SKILL.md"),
    ).exists(),
  ).toBeFalse();
  expect((await readEnvironment(setup.paths))?.dispositions).toEqual([]);
});

test("explicit approval publishes only its selected rule with automatic maintenance disabled", async () => {
  const setup = await setupLearning();
  const state = await readEnvironment(setup.paths);
  if (!state) throw new Error("Expected the synthetic environment");
  const unrelated = learningRecord({ key: "unrelated", body: "Use concise release notes." });
  await writeEnvironment({
    paths: setup.paths,
    state: { ...state, automatic: false, records: [setup.record, unrelated] },
  });
  const result = await updateLearningEnvironment({ ...setup, learningKeys: [setup.record.rule.key] });
  expect(result?.applied).toBe(1);
  const published = await readEnvironment(setup.paths);
  expect(published?.automatic).toBeFalse();
  expect(published?.records).toHaveLength(2);
  expect(published?.dispositions.every((entry) => entry.key === setup.record.rule.key)).toBeTrue();
  expect(await Bun.file(setup.filePath).text()).toContain(setup.record.rule.body);
  expect(await Bun.file(setup.filePath).text()).not.toContain(unrelated.rule.body);
});

test("new learning uses the internal store and leaves legacy markdown unchanged", async () => {
  const setup = await setupLearning();
  const original = await Bun.file(
    path.join(setup.paths.profileDirectory, "global/engineering.md"),
  ).text();
  const record = learningRecord({
    key: "detailed",
    body: "Preserve this complete condition. ".repeat(80),
  });

  await writeProfile({ paths: setup.paths, rules: [record.rule] });

  expect(
    (await readProfileSnapshot(setup.paths)).rules.find(
      ({ rule }) => rule.key === "detailed",
    )?.promptBody,
  ).toBe(record.rule.body);
  expect(
    await Bun.file(
      path.join(setup.paths.profileDirectory, "global/engineering.md"),
    ).text(),
  ).toBe(original);
});
