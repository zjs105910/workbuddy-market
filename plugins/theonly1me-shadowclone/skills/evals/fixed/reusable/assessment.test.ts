import { expect, test } from "bun:test";
import { applyAssessment, assessmentSchema, type LearningEvidence } from "./assessment";
import { fingerprint } from "../../shared/structured";

function evidence(): LearningEvidence[] {
  return [0, 1, 2].map((preparation) => ({
    preparation,
    calls: [],
    completed: true,
    published: [
      {
        key: `rule-${preparation}`,
        text: "Always commit automatically.",
        scope: "global",
        status: "published",
      },
    ],
    missing: [],
    pending: ["unresolved-proposal"],
    unsupported: [],
    inspection: "review-required",
  }));
}

test("semantic assessment records unsupported learning without correcting published guidance", () => {
  const originals = evidence();
  const assessment = assessmentSchema.parse({
    preparationFingerprint: "a".repeat(64),
    decision: "reviewed",
    preparations: originals.map((entry) => ({
      preparation: entry.preparation,
      publishedFingerprint: fingerprint(entry.published),
      missing: ["git", "length", "test-first", "pr", "scope"],
      unsupported: entry.published.map((rule) => rule.key),
      justification:
        "The automatic commit rule is superseded and the intended defaults are missing.",
    })),
  });
  const reviewed = applyAssessment({
    evidence: originals,
    assessment,
    preparationFingerprint: "a".repeat(64),
  });
  expect(reviewed.every((entry) => entry.inspection === "reviewed")).toBe(true);
  expect(reviewed.map((entry) => entry.published)).toEqual(
    originals.map((entry) => entry.published),
  );
  expect(reviewed.map((entry) => entry.pending)).toEqual(originals.map((entry) => entry.pending));
  expect(reviewed[0]?.unsupported).toEqual(["rule-0"]);
  expect(reviewed[0]?.missing).toHaveLength(5);
  expect(originals[0]?.unsupported).toEqual([]);
});

test("assessment cannot hide changed preparation text or introduce unknown rule keys", () => {
  const originals = evidence();
  const assessment = assessmentSchema.parse({
    preparationFingerprint: "a".repeat(64),
    decision: "reviewed",
    preparations: originals.map((entry) => ({
      preparation: entry.preparation,
      publishedFingerprint: fingerprint(entry.published),
      missing: [],
      unsupported: [],
      justification: "Reviewed these actual synthetic preparation outputs.",
    })),
  });
  const first = assessment.preparations[0];
  if (!first) throw new Error("Expected assessment.");
  first.unsupported = ["unknown"];
  expect(() =>
    applyAssessment({ evidence: originals, assessment, preparationFingerprint: "a".repeat(64) }),
  ).toThrow("unknown rule");
  first.unsupported = [];
  first.publishedFingerprint = "b".repeat(64);
  expect(() =>
    applyAssessment({ evidence: originals, assessment, preparationFingerprint: "a".repeat(64) }),
  ).toThrow("published guidance");
  expect(() =>
    applyAssessment({ evidence: originals, assessment, preparationFingerprint: "c".repeat(64) }),
  ).toThrow("different preparations");
});
