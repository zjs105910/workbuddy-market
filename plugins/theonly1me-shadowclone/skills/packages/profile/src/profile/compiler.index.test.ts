import { rule } from "./compiler.index.fixtures";
import { expect, test } from "bun:test";
import { compileProfile, defaultIndexByteBudget } from "./index";

test("the index renders one line per rule with its first sentence and conditions", async () => {
  const compilation = await compileProfile({
    input: {
      kind: "rules",
      rules: [
        rule({
          key: "options",
          title: "Options objects",
          body: "Use one options object for two or more arguments. Positional arguments hide meaning.",
          appliesWhen: ["writing TypeScript"],
        }),
        rule({
          key: "fenced",
          title: "Commit format",
          body: "```\nfeat: add parser\n```",
        }),
      ],
    },
    format: "index",
  });

  expect(compilation.markdown).toContain(
    "- Options objects: Use one options object for two or more arguments. (when writing TypeScript)\n",
  );
  expect(compilation.markdown).toContain("- Commit format\n");
  expect(compilation.markdown).not.toContain(
    "Positional arguments hide meaning",
  );
  expect(compilation.markdown).not.toContain("Guidance source");
  expect(Buffer.byteLength(compilation.markdown, "utf8")).toBe(
    compilation.usedBytes,
  );
});

test("the index stays within 4 KiB by omitting whole lines", async () => {
  const rules = Array.from({ length: 400 }, (_, index) =>
    rule({
      key: `rule-${String(index).padStart(2, "0")}`,
      title: `Rule ${index}`,
      body: `Keep behavior ${"x".repeat(60)} number ${index}.`,
    }),
  );

  const compilation = await compileProfile({
    input: { kind: "rules", rules },
    format: "index",
  });

  expect(Buffer.byteLength(compilation.markdown, "utf8")).toBeLessThanOrEqual(
    defaultIndexByteBudget,
  );
  expect(
    compilation.omissions.filter((omission) => omission.reason === "budget")
      .length,
  ).toBeGreaterThan(0);
  expect(compilation.markdown.endsWith("\n")).toBeTrue();

  for (const line of compilation.markdown
    .split("\n")
    .filter((entry) => entry.startsWith("- "))) {
    expect(line).toMatch(/^- Rule \d+(?:: Keep behavior x+ number \d+\.)?$/);
  }
});

test("the index keeps every short rule before expanding project detail", async () => {
  const globalRules = Array.from({ length: 10 }, (_, index) =>
    rule({
      key: `global-${index}`,
      title: `Global rule ${index}`,
      body: `Keep ${"global ".repeat(20)}detail ${index}.`,
      source: "user",
    }),
  );

  const project = {
    ...rule({
      key: "distance",
      title: "Label distances clearly",
      body: "Print distances in metres and include the unit beside each value.",
    }),
    scope: "project" as const,
    originDirectory: "example.test--fixtures",
    repositoryName: "distance-demo",
  };

  const compilation = await compileProfile({
    input: { kind: "rules", rules: [...globalRules, project] },
    format: "index",
    byteBudget: 600,
  });

  expect(compilation.appliedRuleCount).toBe(11);
  expect(compilation.markdown).toContain(
    "Label distances clearly: Print distances in metres",
  );
  expect(compilation.markdown).toContain("- Global rule 9\n");
  expect(compilation.usedBytes).toBeLessThanOrEqual(600);
});

test("an empty index emits nothing so hooks can stay silent", async () => {
  const compilation = await compileProfile({
    input: { kind: "rules", rules: [] },
    format: "index",
  });

  expect(compilation.markdown).toBe("");
  expect(compilation.appliedRuleCount).toBe(0);
});
