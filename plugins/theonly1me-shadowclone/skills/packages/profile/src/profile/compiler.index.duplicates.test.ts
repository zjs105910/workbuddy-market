import { rule } from "./compiler.index.fixtures";
import { expect, test } from "bun:test";
import { compileProfile } from "./index";

test("a rule already stated in native guidance is omitted as a known duplicate", async () => {
  const compilation = await compileProfile({
    input: {
      kind: "rules",
      rules: [
        rule({
          key: "gate",
          title: "Run the gate",
          body: "Run `bun run check` before presenting any change.",
        }),
        rule({
          key: "names",
          title: "Complete names",
          body: "Use full words in identifiers.",
        }),
      ],
    },
    format: "index",
    knownNativeText: [
      "## Commands\n\nRun bun run check before presenting any change. CI runs the same gate.",
    ],
  });

  expect(compilation.markdown).not.toContain("Run the gate");
  expect(compilation.markdown).toContain(
    "- Complete names: Use full words in identifiers.",
  );
  expect(compilation.omissions).toContainEqual({
    ruleKey: "gate",
    reason: "known-duplicate",
  });
});

test("a short probe is too weak to count as a known duplicate", async () => {
  const compilation = await compileProfile({
    input: {
      kind: "rules",
      rules: [rule({ key: "short", title: "Test", body: "Test it." })],
    },
    format: "index",
    knownNativeText: ["Test it. Always."],
  });

  expect(compilation.markdown).toContain("- Test: Test it.");
});

test("a title that repeats the first sentence is not written twice", async () => {
  const compilation = await compileProfile({
    input: {
      kind: "rules",
      rules: [
        rule({
          key: "size",
          title: "Keep every file under 200 lines",
          body: "Keep every file under 200 lines.",
        }),
      ],
    },
    format: "index",
  });

  expect(compilation.markdown).toContain("- Keep every file under 200 lines\n");
});
