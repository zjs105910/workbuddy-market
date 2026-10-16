import { expect, test } from "bun:test";
import { compileProfile } from "./index";
import type { ProfileRule } from "./index";

function largeRule(options: {
  readonly key: string;
  readonly marker: string;
  readonly body: string;
}): ProfileRule {
  return {
    key: options.key,
    title: options.marker,
    body: options.body,
    section: "engineering",
    scope: "global",
    originDirectory: null,
    repositoryName: null,
    source: "mined",
    status: "active",
    proposal: null,
    appliesWhen: [],
    evidence: { for: [], against: [] },
    observations: 1,
    lastSeen: "2026-09-09",
    sessions: 3,
    origins: [],
    importReference: null,
  };
}

test("the byte budget omits whole rules and never slices UTF-8", async () => {
  const firstBody = "Keep this complete ✅.";
  const secondBody = `Never slice this marker ${"界".repeat(120)}.`;
  const byteBudget = 190;

  const compilation = await compileProfile({
    input: {
      kind: "rules",
      rules: [
        largeRule({ key: "first", marker: "First rule", body: firstBody }),
        largeRule({ key: "second", marker: "Second rule", body: secondBody }),
      ],
    },
    byteBudget,
  });

  expect(Buffer.byteLength(compilation.markdown, "utf8")).toBeLessThanOrEqual(
    byteBudget,
  );
  expect(compilation.markdown).toContain(firstBody);
  expect(compilation.markdown).not.toContain("Second rule");
  expect(compilation.markdown).not.toContain("Never slice this marker");
  expect(compilation.omissions).toContainEqual({
    ruleKey: "second",
    reason: "budget",
  });
});

test("the default compiled profile stays within 16 KiB", async () => {
  const rules = Array.from({ length: 20 }, (_, index) =>
    largeRule({
      key: `rule-${String(index).padStart(2, "0")}`,
      marker: `Rule ${index}`,
      body: "x".repeat(2_000),
    }),
  );

  const compilation = await compileProfile({
    input: { kind: "rules", rules },
  });

  expect(Buffer.byteLength(compilation.markdown, "utf8")).toBeLessThanOrEqual(
    16_384,
  );
  expect(
    compilation.omissions.some((entry) => entry.reason === "budget"),
  ).toBeTrue();
});
