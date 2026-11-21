import { expect, test } from "bun:test";
import { createProjectPaths } from "@shadowclone/core";
import { learningRecord } from "./fixtures";
import { pendingLearningRecords } from "./pending";
import { recordFingerprint } from "./records";
import { emptyEnvironment, type LearningRecord } from "./types";

const paths = createProjectPaths({ homeDirectory: "/private/tmp/synthetic-learning-diagnostics", platform: "darwin" });
const record = learningRecord();
const organization: LearningRecord = {
  ...record,
  rule: { ...record.rule, scope: "org", originDirectory: "synthetic-owner", repositoryName: null },
};

test("unmatched organization learning stays deferred and candidates stay candidates", () => {
  const candidate: LearningRecord = {
    ...organization,
    rule: { ...organization.rule, key: "candidate", status: "candidate" },
  };
  const state = { ...emptyEnvironment, records: [organization, candidate] };
  const result = pendingLearningRecords({ paths, state });

  expect(result.map(({ status }) => status)).toEqual(["unresolved-scope", "candidate"]);
  expect(result[0]?.reason).toContain("No matching registered repository");
  expect(result.every(({ scope }) => scope === "org")).toBeTrue();
  expect(state.dispositions).toEqual([]);
});

test("publication in one repository does not hide another matching repository", () => {
  const state = {
    ...emptyEnvironment,
    records: [organization],
    repositories: ["first", "second"].map((name) => ({
      directory: `/private/tmp/synthetic-learning-diagnostics/${name}`,
      repositoryName: name,
      originDirectory: "synthetic-owner",
    })),
    dispositions: [{
      key: organization.rule.key,
      scope: "synthetic-owner/first",
      status: "published" as const,
      inputFingerprint: recordFingerprint(organization),
      reason: "Published in the first repository",
      destinations: [],
    }],
  };
  const result = pendingLearningRecords({ paths, state });

  expect(result).toHaveLength(1);
  expect(result[0]?.scope).toBe("synthetic-owner/second");
  expect(result[0]?.status).toBe("awaiting-publication");
});

test("contradictions and stale status do not become retirement requests", () => {
  const state = {
    ...emptyEnvironment,
    records: [
      { ...record, rule: { ...record.rule, status: "stale" as const } },
      { ...record, rule: { ...record.rule, key: "conflict", proposal: { kind: "revise" as const, text: "Review this alternative" } } },
    ],
  };

  expect(pendingLearningRecords({ paths, state }).map(({ status }) => status))
    .toEqual(["retirement-review", "conflicting-evidence"]);
});
