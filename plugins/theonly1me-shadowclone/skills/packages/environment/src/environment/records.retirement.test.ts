import { expect, test } from "bun:test";
import { rm } from "node:fs/promises";
import { profileRulePath } from "@shadowclone/profile";
import { skillFixture } from "./testing";
import { learningRecord } from "./fixtures";
import { storeLearningRules } from "./records";
import { readEnvironment, writeEnvironment } from "./store";
import { emptyEnvironment } from "./types";

test("only an explicit matching retirement records removal authority", async () => {
  const setup = await skillFixture();
  const record = learningRecord();

  try {
    await writeEnvironment({ paths: setup.paths, state: { ...emptyEnvironment, records: [record] } });
    await storeLearningRules({ paths: setup.paths, rules: [{ ...record.rule, status: "stale" }] });
    expect((await readEnvironment(setup.paths))?.records[0]?.retirementRequested).toBeUndefined();

    await storeLearningRules({ paths: setup.paths, rules: [], retired: [{ key: record.rule.key, relativePath: "different/scope.md" }] });
    expect((await readEnvironment(setup.paths))?.records[0]?.retirementRequested).toBeUndefined();

    await storeLearningRules({ paths: setup.paths, rules: [{
      ...record.rule, status: "stale", proposal: { kind: "revise", text: "An earlier unresolved alternative" },
    }] });
    await storeLearningRules({ paths: setup.paths, rules: [], retired: [{ key: record.rule.key, relativePath: profileRulePath(record.rule) }] });
    expect((await readEnvironment(setup.paths))?.records[0]?.retirementRequested).toBeTrue();
    expect((await readEnvironment(setup.paths))?.records[0]?.rule.status).toBe("stale");
    expect((await readEnvironment(setup.paths))?.records[0]?.rule.proposal).toBeNull();

    await storeLearningRules({ paths: setup.paths, rules: [record.rule] });
    expect((await readEnvironment(setup.paths))?.records[0]?.retirementRequested).toBeUndefined();
  } finally {
    await rm(setup.home, { recursive: true, force: true });
  }
});
