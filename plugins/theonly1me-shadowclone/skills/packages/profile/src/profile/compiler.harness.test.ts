import { expect, test } from "bun:test";
import { compileProfile } from "./index";
import type { ProfileRule, RepositoryApplicability } from "./index";

function rule(options: {
  readonly key: string;
  readonly title: string;
  readonly body: string;
}): ProfileRule {
  return {
    key: options.key,
    title: options.title,
    body: options.body,
    section: "engineering",
    scope: "global",
    originDirectory: null,
    repositoryName: null,
    source: "declared",
    status: "active",
    proposal: null,
    appliesWhen: [],
    evidence: { for: [], against: [] },
    observations: 1,
    lastSeen: "2026-09-26",
    sessions: 1,
    origins: [],
    importReference: null,
  };
}

const pythonRepository: RepositoryApplicability = {
  tools: new Set(["python", "pytest"]),
  entries: new Set(["pyproject.toml", "src", "tests"]),
};

async function harness(rules: readonly ProfileRule[]) {
  return compileProfile({
    input: { kind: "rules", rules },
    format: "harness",
    applicability: pythonRepository,
  });
}

test("the harness format renders rule lines without the session preamble", async () => {
  const compilation = await harness([
    rule({
      key: "names",
      title: "Complete names",
      body: "Use full words in identifiers.",
    }),
  ]);

  expect(compilation.markdown).toBe(
    "- Complete names: Use full words in identifiers.\n",
  );
});

test("a rule that names only tools the repository lacks is not applicable", async () => {
  const compilation = await harness([
    rule({
      key: "bun",
      title: "Bun tests",
      body: "Run `bun test` before presenting.",
    }),
    rule({
      key: "mixed",
      title: "No suppressions",
      body: "Never add eslint-disable or a pytest skip to get green.",
    }),
    rule({
      key: "generic",
      title: "Small files",
      body: "Keep every file under 200 lines.",
    }),
  ]);

  expect(compilation.markdown).not.toContain("Bun tests");
  expect(compilation.markdown).toContain("- No suppressions:");
  expect(compilation.markdown).toContain("- Small files:");
  expect(compilation.omissions).toContainEqual({
    ruleKey: "bun",
    reason: "not-applicable",
  });
});

test("a rule that points into a missing top-level path is not applicable, but a slashed concept is kept", async () => {
  const compilation = await harness([
    rule({
      key: "roadmap",
      title: "Roadmap",
      body: "Read `docs/architecture/06-roadmap.md` first.",
    }),
    rule({
      key: "tests",
      title: "Test layout",
      body: "Put tests under `tests/unit/` beside fixtures.",
    }),
    rule({
      key: "owner",
      title: "Owner isolation",
      body: "Rules stay inside one `host/owner` scope.",
    }),
  ]);

  expect(compilation.omissions).toContainEqual({
    ruleKey: "roadmap",
    reason: "not-applicable",
  });
  expect(compilation.markdown).toContain("- Test layout:");
  expect(compilation.markdown).toContain("- Owner isolation:");
});
