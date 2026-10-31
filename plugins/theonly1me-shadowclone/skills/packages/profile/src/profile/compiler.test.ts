import { expect, test } from "bun:test";
import { mkdir, mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import type { OriginScope } from "@shadowclone/sessions";
import { compileProfile, renderProfileRule } from "./index";
import type { ProfileRule } from "./index";

const acmeOrigin: OriginScope = {
  id: "github.com/acme",
  directoryName: "github.com--acme--936913df4a5c268b",
  promotable: true,
};

function profileRule(options: {
  readonly key: string;
  readonly title: string;
  readonly source: ProfileRule["source"];
  readonly status?: ProfileRule["status"];
  readonly appliesWhen?: readonly string[];
  readonly observations?: number;
}): ProfileRule {
  return {
    key: options.key,
    title: options.title,
    body: `Follow ${options.title.toLowerCase()}.`,
    section: "workflow",
    scope: "global",
    originDirectory: null,
    repositoryName: null,
    source: options.source,
    status: options.status ?? "active",
    proposal: null,
    appliesWhen: options.appliesWhen ?? [],
    evidence: { for: [], against: [] },
    observations: options.observations ?? 0,
    lastSeen: "2026-09-09",
    sessions: 0,
    origins: [],
    importReference: null,
  };
}

test("compiles redacted scoped guidance with source and condition labels", async () => {
  const profileDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-compiler-"),
  );
  const globalDirectory = path.join(profileDirectory, "global");

  await mkdir(globalDirectory, { recursive: true });

  const rules = [
    profileRule({
      key: "declared",
      title: "Plan before editing",
      source: "declared",
      appliesWhen: ["starting an implementation task"],
    }),
    profileRule({
      key: "candidate",
      title: "Unconfirmed preference",
      source: "mined",
      status: "candidate",
    }),
    profileRule({
      key: "stale",
      title: "Contradicted preference",
      source: "mined",
      status: "stale",
    }),
  ];

  await Bun.write(
    path.join(globalDirectory, "workflow.md"),
    rules.map(renderProfileRule).join("\n\n"),
  );

  const compilation = await compileProfile({
    input: {
      kind: "directory",
      profileDirectory,
      origin: acmeOrigin,
      targetRepo: null,
    },
  });

  expect(compilation.markdown).toContain("Plan before editing");
  expect(compilation.markdown).toContain(
    "Guidance source: declared by the user",
  );
  expect(compilation.markdown).toContain(
    "Applies when: starting an implementation task",
  );
  expect(compilation.markdown).not.toContain("Unconfirmed preference");
  expect(compilation.markdown).not.toContain("Contradicted preference");
  expect(compilation.appliedRuleKeys).toEqual(["declared"]);
  expect(compilation.omissions).toEqual([
    { ruleKey: "candidate", reason: "candidate" },
    { ruleKey: "stale", reason: "stale" },
  ]);
});

test("a user-owned seed choice wins an active axis conflict", async () => {
  const compilation = await compileProfile({
    input: {
      kind: "rules",
      rules: [
        profileRule({
          key: "seed:planning-when-costly",
          title: "Plan only costly changes",
          source: "mined",
          observations: 20,
        }),
        profileRule({
          key: "seed:planning-first",
          title: "Plan before changing code",
          source: "declared",
        }),
      ],
    },
  });

  expect(compilation.markdown).toContain("Plan before changing code");
  expect(compilation.markdown).not.toContain("Plan only costly changes");
  expect(compilation.omissions).toContainEqual({
    ruleKey: "seed:planning-when-costly",
    reason: "axis-conflict",
  });
});

test("identical compiler inputs produce identical results", async () => {
  const options = {
    input: {
      kind: "rules" as const,
      rules: [
        profileRule({
          key: "stable",
          title: "Keep stable output",
          source: "mined",
        }),
      ],
    },
  };

  expect(await compileProfile(options)).toEqual(await compileProfile(options));
});
