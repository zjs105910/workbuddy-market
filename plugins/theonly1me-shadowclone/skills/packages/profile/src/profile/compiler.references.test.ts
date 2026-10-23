import { expect, test } from "bun:test";
import { mkdir, mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { canonicalPath } from "@shadowclone/core";
import {
  readScopedReferences,
  parseReference,
  referenceRelativePath,
  renderReference,
} from "../references";
import { compileProfile, renderProfileRule } from "./index";
import type { ProfileRule, ProfileSource } from "./index";

function rule(options: {
  readonly key: string;
  readonly source: ProfileSource;
  readonly body?: string;
  readonly observations?: number;
}): ProfileRule {
  return {
    key: options.key,
    title: options.key,
    body: options.body ?? `Apply ${options.key}.`,
    section: "workflow",
    scope: "global",
    originDirectory: null,
    repositoryName: null,
    source: options.source,
    status: "active",
    proposal: null,
    appliesWhen: [],
    evidence: { for: [], against: [] },
    observations: options.observations ?? 0,
    lastSeen: "2026-09-18",
    sessions: 1,
    origins: [],
    importReference: null,
  };
}

test("compiler priority keeps references ahead of imported guidance", async () => {
  const profileDirectory = canonicalPath(
    await mkdtemp(path.join(os.tmpdir(), "shadowclone-priority-")),
  );

  const rules = [
    rule({ key: "user", source: "user" }),
    rule({ key: "declared", source: "declared" }),
    rule({ key: "mined", source: "mined" }),
    rule({
      key: "imported",
      source: "imported",
      body: "Imported text ".repeat(200).trim(),
      observations: 10_000,
    }),
  ];

  await mkdir(path.join(profileDirectory, "global"), { recursive: true });
  await Bun.write(
    path.join(profileDirectory, "global", "workflow.md"),
    rules.map(renderProfileRule).join("\n\n"),
  );

  const reference = {
    schema: 1 as const,
    key: "reference-key",
    title: "Reference title",
    summary: "A scoped summary.",
    tags: ["scope"],
    scope: "global" as const,
    originDirectory: null,
    repositoryName: null,
    source: "user" as const,
    sourceLocator: "reference.md",
    updatedAt: "2026-09-18",
    body: "Full detail remains on demand.",
  };

  const referencePath = path.join(
    profileDirectory,
    referenceRelativePath(reference),
  );

  await mkdir(path.dirname(referencePath), { recursive: true });
  await Bun.write(referencePath, renderReference(reference));

  const recallOnly = {
    ...reference,
    key: "active-project-note",
    title: "Active project note",
    source: "claude-project-memory" as const,
    sourceLocator: "project_active.md",
  };

  const recallOnlyPath = path.join(
    profileDirectory,
    referenceRelativePath(recallOnly),
  );

  await Bun.write(recallOnlyPath, renderReference(recallOnly));

  expect(parseReference(await Bun.file(referencePath).text())).not.toBeNull();

  const referenceFiles = await Array.fromAsync(
    new Bun.Glob("*.md").scan({
      cwd: path.dirname(referencePath),
      absolute: true,
      onlyFiles: true,
    }),
  );

  expect(referenceFiles.sort()).toEqual([recallOnlyPath, referencePath].sort());
  expect(
    await readScopedReferences({
      profileDirectory,
      origin: null,
      targetRepo: null,
    }),
  ).toHaveLength(2);

  const main = await compileProfile({
    input: {
      kind: "directory",
      profileDirectory,
      origin: null,
      targetRepo: null,
    },
    repositoryContext: "missing",
    byteBudget: 1_000,
  });

  expect(main.markdown).toContain("user");
  expect(main.markdown).toContain("declared");
  expect(main.markdown).toContain("mined");
  expect(main.markdown).toContain("reference-key");
  expect(main.markdown).not.toContain("active-project-note");
  expect(main.markdown).not.toContain("Imported text");
  expect(main.omissions).toContainEqual({
    ruleKey: "imported",
    reason: "budget",
  });
  expect(main.usedBytes).toBe(Buffer.byteLength(main.markdown, "utf8"));

  const subagent = await compileProfile({
    input: {
      kind: "directory",
      profileDirectory,
      origin: null,
      targetRepo: null,
    },
    audience: "subagent",
    repositoryContext: "missing",
    byteBudget: 1_000,
  });

  expect(subagent.markdown).not.toContain("reference-key");
  expect(subagent.appliedReferenceCount).toBe(0);

  const native = await compileProfile({
    input: {
      kind: "directory",
      profileDirectory,
      origin: null,
      targetRepo: null,
    },
  });

  expect(native.markdown).not.toContain("Imported text");
  expect(native.omissions).toContainEqual({
    ruleKey: "imported",
    reason: "native-duplicate",
  });
});
