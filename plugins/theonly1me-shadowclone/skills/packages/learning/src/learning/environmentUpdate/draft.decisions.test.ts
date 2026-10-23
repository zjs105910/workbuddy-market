import { expect, test } from "bun:test";
import { applySkillDraft } from "./draft";
import { authorizeDraftOutcomes } from "@shadowclone/environment";
import { learningRecord } from "@shadowclone/environment/testing";

const record = learningRecord({ key: "approval", body: "Ask before changing release tags." });
const draft = {
  description: "",
  body: "",
  outcomes: [{ key: record.rule.key, disposition: "retire" as const, reason: "Retirement was requested" }],
  edits: [{ before: record.rule.body, after: "Keep the remaining checks.", keys: [record.rule.key] }],
};
const original = `---\nname: release-checks\ndescription: Check release changes\n---\n\n${record.rule.body}\n`;

test("active and unconfirmed stale records cannot authorize a removal", () => {
  for (const status of ["active", "stale"] as const) {
    const supplied = { ...record, rule: { ...record.rule, status } };
    const authorized = authorizeDraftOutcomes({ draft, records: [supplied] });

    expect(authorized.outcomes[0]?.disposition).toBe("pending");
    expect(authorized.outcomes[0]?.reason).toContain("No explicit retirement");
    expect(() => applySkillDraft({
      draft, original, name: "release-checks", description: "", records: [supplied],
    })).toThrow("requires review");
  }
});

test("a recorded retirement removes only its exact section", () => {
  const retired = { ...record, retirementRequested: true as const, rule: { ...record.rule, status: "stale" as const } };
  const result = applySkillDraft({
    draft, original, name: "release-checks", description: "", records: [retired],
  });

  expect(result).not.toContain(record.rule.body);
  expect(result).toContain("Keep the remaining checks.");
});

test("outcomes cannot omit, duplicate, or invent a learning key", () => {
  for (const outcomes of [[], [...draft.outcomes, ...draft.outcomes], [{ ...draft.outcomes[0], key: "unknown", disposition: "pending" as const, reason: "Unknown" }]]) {
    expect(() => authorizeDraftOutcomes({ draft: { ...draft, outcomes }, records: [record] }))
      .toThrow("every supplied learning");
  }
});
