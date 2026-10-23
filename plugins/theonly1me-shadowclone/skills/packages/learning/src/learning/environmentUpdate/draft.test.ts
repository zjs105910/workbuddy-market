import { expect, test } from "bun:test";
import { applySkillDraft } from "./draft";
import { learningRecord } from "@shadowclone/environment/testing";
import { fixtureSkill } from "@shadowclone/skills/testing";

const record = learningRecord();

const draft = {
  outcomes: [{ key: record.rule.key, disposition: "apply" as const, reason: "Supported prerequisite" }],
  description: "",
  body: "",
  edits: [
    {
      before: "Preserve the requested behavior.",
      after: `Preserve the requested behavior. ${record.rule.body}`,
      keys: [record.rule.key],
    },
  ],
};

test("section edits preserve unrelated instructions and invocation permissions", () => {
  const original = `${fixtureSkill()}\nLeave existing assets alone.\n`;

  const result = applySkillDraft({
    draft,
    original,
    name: "typed-changes",
    description: "",
    records: [record],
  });

  expect(result).toContain(record.rule.body);
  expect(result).toContain("disable-model-invocation: true");
  expect(result).toContain("Leave existing assets alone.");
});

test("ambiguous edits and invented evidence cannot change a skill", () => {
  const options = {
    draft,
    original: `${fixtureSkill()}\nPreserve the requested behavior.`,
    name: "typed-changes",
    description: "",
    records: [record],
  };

  expect(() => applySkillDraft(options)).toThrow("one exact section");
  expect(() =>
    applySkillDraft({ ...options, draft: { ...draft, outcomes: [] } }),
  ).toThrow("every supplied learning");
  expect(() =>
    applySkillDraft({
      ...options,
      original: fixtureSkill(),
      draft: {
        ...draft,
        edits: [
          {
            ...draft.edits[0],
            before: "Preserve the requested behavior.",
            after: "Changed",
            keys: ["invented"],
          },
        ],
      },
    }),
  ).toThrow("unknown learning");
});

test("baseline overflow fails without truncating the learning", () => {
  expect(() =>
    applySkillDraft({
      draft: { ...draft, edits: [], body: "A".repeat(4100) },
      original: null,
      name: "shadowclone-baseline",
      description: "Always load",
      records: [record],
    }),
  ).toThrow("4 KiB");
});

test("missing skill metadata is repaired without changing invocation settings or unrelated text", () => {
  const original =
    "---\nname: typed-changes\ndisable-model-invocation: true\n---\n\nPreserve the requested behavior.\n";

  const result = applySkillDraft({
    draft,
    original,
    name: "typed-changes",
    description: "Use for typed changes",
    records: [record],
  });

  expect(result).toContain("disable-model-invocation: true");
  expect(result).toContain("description: Use for typed changes");
  expect(result).toContain(record.rule.body);
  expect(() =>
    applySkillDraft({
      draft,
      original: original.replace(
        "name: typed-changes",
        "name: typed-changes\nname: different",
      ),
      name: "typed-changes",
      description: "Use for typed changes",
      records: [record],
    }),
  ).toThrow("duplicate fields");
});
