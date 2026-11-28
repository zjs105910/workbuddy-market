import { expect, test } from "bun:test";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { createProjectPaths } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";
import { parseProfileRules, profileRulePath } from "@shadowclone/profile";
import { readGeneratedProfileState, readProfileRejections } from "@shadowclone/profile";
import type { ProfileRule } from "@shadowclone/profile";
import { writeProfile } from "./profileRecords";

async function createTestPaths(): Promise<ProjectPaths> {
  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-lifecycle-"),
  );

  return createProjectPaths({ homeDirectory, platform: "darwin" });
}

function profileRule(options: {
  readonly key: string;
  readonly title: string;
  readonly body: string;
}): ProfileRule {
  return {
    ...options,
    section: "workflow",
    scope: "org",
    originDirectory: "github.com--acme",
    repositoryName: null,
    source: "mined",
    status: "active",
    proposal: null,
    appliesWhen: [],
    evidence: { for: ["event:one"], against: [] },
    observations: 1,
    lastSeen: "2026-09-08",
    sessions: 1,
    origins: ["github.com/acme"],
    importReference: null,
  };
}

test("revises wording without changing the persisted key", async () => {
  const paths = await createTestPaths();
  const original = profileRule({
    key: "persistent-rule",
    title: "Run focused checks",
    body: "Run one focused check.",
  });
  const revised = {
    ...original,
    title: "Verify the changed behavior",
    body: "Run the narrow check that proves the requested behavior.",
  };

  await writeProfile({ paths, rules: [original] });

  await writeProfile({ paths, rules: [revised] });

  const filePath = path.join(paths.profileDirectory, profileRulePath(revised));
  const [parsed] = parseProfileRules(await Bun.file(filePath).text());

  expect(parsed?.key).toBe(original.key);
  expect(parsed?.title).toBe(revised.title);
  expect(await Bun.file(filePath).text()).not.toContain(original.title);
});

test("keeps a rejected identity rejected after its wording changes", async () => {
  const paths = await createTestPaths();
  const original = profileRule({
    key: "rejected-rule",
    title: "Run focused checks",
    body: "Run one focused check.",
  });

  await writeProfile({ paths, rules: [original] });

  const filePath = path.join(paths.profileDirectory, profileRulePath(original));

  await rm(filePath);

  const revised = {
    ...original,
    title: "Verify the changed behavior",
    body: "Run the narrow check for the changed behavior.",
  };

  await writeProfile({ paths, rules: [revised] });

  const [rejection] = await readProfileRejections(paths.rejectedProfileFile);

  expect(await Bun.file(filePath).exists()).toBeFalse();
  expect(rejection).toMatchObject({
    key: original.key,
    title: original.title,
    body: original.body,
    source: "mined",
  });
});

test("retires generated guidance without recording a user rejection", async () => {
  const paths = await createTestPaths();
  const rule = profileRule({
    key: "retired-rule",
    title: "Retire this",
    body: "This generated guidance is obsolete.",
  });

  await writeProfile({ paths, rules: [rule] });

  const relativePath = profileRulePath(rule);

  await writeProfile({
    paths,
    rules: [],
    retired: [{ relativePath, key: rule.key }],
  });

  const generated = await readGeneratedProfileState(paths.profileManifestFile);

  expect(
    await Bun.file(path.join(paths.profileDirectory, relativePath)).exists(),
  ).toBeFalse();
  expect(generated).toContainEqual(
    expect.objectContaining({ key: rule.key, disposition: "retired" }),
  );
  expect(await readProfileRejections(paths.rejectedProfileFile)).toEqual([]);
});
