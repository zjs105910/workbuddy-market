import { expect, test } from "bun:test";
import path from "node:path";
import { readPendingLearning, updatePendingLearning } from "./pending";
import { learningRecord } from "@shadowclone/environment/testing";
import {
  emptyEnvironment,
  environmentFile,
  readEnvironment,
  undoRevision,
  writeEnvironment,
} from "@shadowclone/environment";
import { preferenceEditFixture } from "./testing";
import { applyPreferencePreview, previewPreferenceEdit, previewSourceRemoval } from "./lifecycle";

test("replacement previews write nothing, reject stale state, and can be undone", async () => {
  const { paths, record } = await preferenceEditFixture();
  const before = await Bun.file(environmentFile(paths)).text();
  const preview = await previewPreferenceEdit({
    paths, edit: { kind: "replace", key: record.rule.key, text: "Validate palette labels before saving." },
  });
  expect(await Bun.file(environmentFile(paths)).text()).toBe(before);
  const result = await applyPreferencePreview({ paths, preview });
  expect((await readEnvironment(paths))?.records[0]?.rule.body).toBe("Validate palette labels before saving.");
  await expect(applyPreferencePreview({ paths, preview })).rejects.toThrow("changed since preview");
  if (!result.revision) throw new Error("Expected a preference decision revision");
  await undoRevision({ paths, id: result.revision });
  expect(await Bun.file(environmentFile(paths)).text()).toBe(before);
});

test("narrowing retires the old global rule and keeps a distinct repository rule", async () => {
  const { paths, record, home } = await preferenceEditFixture();
  const preview = await previewPreferenceEdit({
    paths, edit: { kind: "narrow", key: record.rule.key }, cwd: path.join(home, "repository"),
    readRemote: async () => "git@github.com:acme/palette.git",
  });
  expect(preview.changes).toHaveLength(2);
  const narrowed = preview.changes[1]?.after;
  expect(narrowed?.rule.scope).toBe("project");
  expect(narrowed?.rule.key).not.toBe(record.rule.key);
  await applyPreferencePreview({ paths, preview });
  const state = await readEnvironment(paths);
  expect(state?.records.find(({ rule }) => rule.key === record.rule.key)?.retirementRequested).toBeTrue();
  expect(state?.rejected).toContain(record.rule.key);
  expect(state?.records.find(({ rule }) => rule.key === narrowed?.rule.key)?.rule.body).toBe(record.rule.body);
});

test("source-removal previews retain mixed and unresolved evidence for explicit review", async () => {
  const { paths, record } = await preferenceEditFixture();
  await writeEnvironment({
    paths,
    state: {
      ...emptyEnvironment,
      records: [
        { ...record, captureSources: ["codex"], provenanceComplete: true },
        { ...learningRecord({ key: "mixed" }), captureSources: ["codex", "claude-code"], provenanceComplete: true },
        { ...learningRecord({ key: "unresolved" }), rule: { ...record.rule, key: "unresolved", source: "mined" } },
      ],
    },
  });
  const preview = await previewSourceRemoval({ paths, source: "codex" });
  expect(preview.preview.changes.map(({ after }) => after.rule.key)).toEqual([record.rule.key]);
  expect(preview.mixed).toEqual(["mixed"]);
  expect(preview.unresolved).toEqual(["unresolved"]);
  await applyPreferencePreview({ paths, preview: preview.preview });
  expect((await readEnvironment(paths))?.records.filter(({ retirementRequested }) => retirementRequested)).toHaveLength(1);
});

test("source removal and undo restore both preference state and pending decisions", async () => {
  const { paths, record } = await preferenceEditFixture();
  await writeEnvironment({ paths, state: { ...emptyEnvironment,
    records: [{ ...record, captureSources: ["codex"], provenanceComplete: true }],
  } });
  const pendingRule = { ...record.rule, key: "pending-synthetic" };
  await updatePendingLearning({ paths, update: (state) => ({
    ...state, rules: [pendingRule], provenance: { [pendingRule.key]: { sources: ["codex"], complete: true } },
  }) });
  const before = await readPendingLearning(paths);
  const preview = await previewSourceRemoval({ paths, source: "codex" });
  const result = await applyPreferencePreview({ paths, preview: preview.preview });
  expect((await readPendingLearning(paths)).rules).toEqual([]);
  expect((await readPendingLearning(paths)).rejectedKeys).toContain(pendingRule.key);
  expect((await readEnvironment(paths))?.records[0]?.retirementRequested).toBeTrue();
  if (!result.revision) throw new Error("Expected a source-removal revision");
  await undoRevision({ paths, id: result.revision });
  expect(await readPendingLearning(paths)).toEqual(before);
  expect((await readEnvironment(paths))?.records[0]?.retirementRequested).toBeUndefined();
});
