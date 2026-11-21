import { expect, test } from "bun:test";
import { mkdir, mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import type { OriginScope } from "@shadowclone/sessions";
import {
  compileProfile,
  explicitProfileEvidence,
  parseProfileRules,
  renderProfileRule,
} from "./index";
import type { ProfileRule } from "./index";
import { profileRuleSchema } from "./metadata";

const completeRule: ProfileRule = {
  key: "018f7d34-45aa-7a3c-8912-61fc10928d67",
  title: "Verify focused behavior",
  body: "Run the narrow check before presenting the change.",
  section: "workflow",
  scope: "org",
  originDirectory: "github.com--acme--936913df4a5c268b",
  repositoryName: null,
  source: "declared",
  status: "active",
  proposal: {
    kind: "narrow",
    text: "Run only the check that exercises the changed behavior.",
  },
  appliesWhen: ["task=code-change", "language=typescript"],
  evidence: {
    for: ["event:one", "event:one", "event:two"],
    against: ["event:three", "event:three"],
  },
  observations: 3,
  lastSeen: "2026-09-08",
  sessions: 2,
  origins: ["github.com/acme"],
  importReference: null,
};

test("round-trips every profile record field and deduplicates evidence", () => {
  const rendered = renderProfileRule(completeRule);
  const [parsed] = parseProfileRules(rendered);

  expect(parsed).toMatchObject({
    key: completeRule.key,
    title: completeRule.title,
    body: completeRule.body,
    source: "declared",
    status: "active",
    proposal: completeRule.proposal,
    appliesWhen: completeRule.appliesWhen,
    evidence: {
      for: ["event:one", "event:two"],
      against: ["event:three"],
    },
    observations: 3,
    lastSeen: "2026-09-08",
    sessions: 2,
    origins: ["github.com/acme"],
    scope: "org",
    legacy: false,
  });
  expect(rendered).toContain('"supports":2');
  expect(rendered).toContain('"contradicts":1');
});

test("requires location fields that agree with profile scope", () => {
  expect(
    profileRuleSchema.safeParse({
      ...completeRule,
      scope: "project",
      repositoryName: null,
    }).success,
  ).toBeFalse();
  expect(
    profileRuleSchema.safeParse({
      ...completeRule,
      scope: "global",
      originDirectory: "github.com--acme--936913df4a5c268b",
      repositoryName: null,
    }).success,
  ).toBeFalse();
});

test("round-trips opaque import identity", () => {
  const importReference = {
    repositoryAliases: ["a".repeat(64)],
    sourceLocator: "b".repeat(64),
  };
  const [parsed] = parseProfileRules(
    renderProfileRule({ ...completeRule, importReference }),
  );

  expect(parsed?.importReference).toEqual(importReference);
});

test("keeps adversarial proposal text inside one metadata comment", () => {
  const proposal = "Replace this --> with <!-- escaped metadata.";
  const rendered = renderProfileRule({
    ...completeRule,
    proposal: { kind: "revise", text: proposal },
  });
  const [parsed] = parseProfileRules(rendered);

  expect(rendered.match(/<!-- shadowclone:/g)).toHaveLength(1);
  expect(parsed?.proposal?.text).toBe(proposal);
});

test("treats edited generated wording as active user guidance", () => {
  const rendered = renderProfileRule({
    ...completeRule,
    status: "candidate",
    proposal: { kind: "revise", text: "Use different wording." },
  });
  const edited = rendered.replace(
    completeRule.body,
    "Use the wording the user wrote.",
  );
  const [parsed] = parseProfileRules(edited);

  expect(parsed?.source).toBe("user");
  expect(parsed?.status).toBe("active");
  expect(parsed?.proposal).toBeNull();
});

test("compiles contradicted declared guidance while withholding inactive rules", async () => {
  const profileDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-record-"),
  );
  const directory = path.join(
    profileDirectory,
    "org",
    completeRule.originDirectory ?? "isolated",
  );

  await mkdir(directory, { recursive: true });
  await Bun.write(
    path.join(directory, "workflow.md"),
    [
      renderProfileRule({
        ...completeRule,
        evidence: { for: ["event:one"], against: ["event:two"] },
        proposal: { kind: "retire", text: "Stop applying this rule." },
      }),
      renderProfileRule({
        ...completeRule,
        key: "candidate-rule",
        title: "Candidate guidance",
        status: "candidate",
        proposal: null,
      }),
      renderProfileRule({
        ...completeRule,
        key: "explicit-candidate-rule",
        title: "Explicit candidate guidance",
        status: "candidate",
        proposal: null,
        evidence: {
          for: completeRule.evidence.for.map(explicitProfileEvidence),
          against: [],
        },
      }),
      renderProfileRule({
        ...completeRule,
        key: "stale-rule",
        title: "Stale guidance",
        status: "stale",
        proposal: null,
      }),
    ].join("\n\n"),
  );

  const origin: OriginScope = {
    id: "github.com/acme",
    directoryName: "github.com--acme--936913df4a5c268b",
    promotable: true,
  };

  const compilation = await compileProfile({
    input: { kind: "directory", profileDirectory, origin, targetRepo: null },
  });

  expect(compilation.markdown).toContain(completeRule.title);
  expect(compilation.markdown).toContain("Explicit candidate guidance");
  expect(compilation.markdown).not.toContain("Candidate guidance");
  expect(compilation.markdown).not.toContain("Stale guidance");
});
