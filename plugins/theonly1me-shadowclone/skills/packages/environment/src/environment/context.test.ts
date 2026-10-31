import { expect, test } from "bun:test";
import { learningRecord } from "./fixtures";
import { recordFingerprint } from "./records";
import { emptyEnvironment } from "./types";
import { renderSkillRouting } from "./context";

const globalScope = {
  key: "global",
  directory: "/home/synthetic",
  repository: null,
};

const baseline = {
  filePath: "/home/synthetic/.agents/skills/shadowclone-baseline/SKILL.md",
  fingerprint: "hash",
  original: null,
  kind: "skill" as const,
  scope: "global",
  name: "shadowclone-baseline",
  description: "Always load",
  learningKeys: ["style"],
};

test("startup includes short published rules without personal skill paths", () => {
  const record = learningRecord({ body: "Reject duplicate colors before export." });
  const text = renderSkillRouting({
    scopes: [globalScope],
    state: {
      ...emptyEnvironment,
      artifacts: [baseline],
      records: [record],
      dispositions: [{
        scope: "global",
        key: record.rule.key,
        inputFingerprint: recordFingerprint(record),
        status: "published",
        reason: "Published",
        destinations: [baseline.filePath],
      }],
      facts: [
        {
          scope: "another-repository",
          text: "Restricted repository detail",
          learningKeys: ["fact"],
        },
      ],
    },
  });

  expect(text).toContain("Reject duplicate colors before export.");
  expect(text).not.toContain(baseline.filePath);
  expect(text).not.toContain("Restricted repository detail");
  expect(text).not.toContain("profile");
});

test("routing overflow is explicit and never drops a fact", () => {
  expect(() =>
    renderSkillRouting({
      scopes: [globalScope],
      state: {
        ...emptyEnvironment,
        facts: [
          { scope: "global", text: "x".repeat(4096), learningKeys: ["fact"] },
        ],
      },
    }),
  ).toThrow("of 4096 bytes");
});
