import { expect, test } from "bun:test";
import type { ProfileFile } from "./files";
import { assertProfileRetention, droppedProfileRuleKeys } from "./retention";

function storedFile(keys: readonly string[]): ProfileFile {
  return {
    relativePath: "org/github.com--acme/workflow.md",
    filePath: "/tmp/workflow.md",
    content: "",
    blocks: keys.map((key) => ({
      key,
      title: key,
      body: "",
      source: "mined",
      status: "active",
      proposal: null,
      appliesWhen: [],
      evidence: { for: [], against: [] },
      observations: 1,
      lastSeen: "2026-09-05",
      sessions: 1,
      origins: [],
      scope: "org",
      importReference: null,
      fingerprint: "abc",
      content: "",
      edited: false,
      legacy: false,
    })),
  };
}

test("reports a stored rule that no branch wrote back", () => {
  expect(
    droppedProfileRuleKeys({
      files: [storedFile(["kept", "vanished"])],
      written: new Set(["kept"]),
      retired: new Set(),
    }),
  ).toEqual(["vanished"]);
});

test("accepts a stored rule removed through an explicit retirement", () => {
  expect(() =>
    assertProfileRetention({
      files: [storedFile(["kept", "retired"])],
      written: new Set(["kept"]),
      retired: new Set(["retired"]),
    }),
  ).not.toThrow();
});

test("refuses a write that would silently remove stored rules", () => {
  expect(() =>
    assertProfileRetention({
      files: [storedFile(["one", "two", "three"])],
      written: new Set(["one"]),
      retired: new Set(),
    }),
  ).toThrow("would remove 2 stored rule(s)");
});
