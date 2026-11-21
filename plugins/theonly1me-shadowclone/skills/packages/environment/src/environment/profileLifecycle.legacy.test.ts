import { expect, test } from "bun:test";
import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { createProjectPaths } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";
import { parseProfileRules, profileFingerprint } from "@shadowclone/profile";
import { readGeneratedProfileState } from "@shadowclone/profile";
import { writeProfile } from "./profileRecords";

async function createTestPaths(): Promise<ProjectPaths> {
  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-legacy-"),
  );

  return createProjectPaths({ homeDirectory, platform: "darwin" });
}

function profileRule(options: {
  readonly key: string;
  readonly title: string;
  readonly body: string;
}) {
  return {
    ...options,
    section: "workflow" as const,
    scope: "org" as const,
    originDirectory: "github.com--acme",
    repositoryName: null,
    source: "mined" as const,
    status: "active" as const,
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

function legacyBlock(options: {
  readonly key: string;
  readonly visible: string;
  readonly fingerprint: string;
  readonly sessions?: number;
}): string {
  return [
    options.visible,
    "",
    `<!-- shadowclone: key=${options.key} observations=2 confidence=0.80 last-seen=2026-09-05 sessions=${options.sessions ?? 1} origins=github.com/acme scope=org fingerprint=${options.fingerprint} -->`,
  ].join("\n");
}

test("migrates unedited legacy guidance instead of deleting it", async () => {
  const paths = await createTestPaths();
  const relativePath = "org/github.com--acme/workflow.md";
  const filePath = path.join(paths.profileDirectory, relativePath);
  const minedVisible =
    "## Hold the stated scope\n\nReport adjacent findings instead of folding them in.";
  const originalEditedVisible =
    "## Review changes\n\nReview every generated change.";
  const editedVisible =
    "## Review changes\n\nReview the focused diff before continuing.";
  const mined = legacyBlock({
    key: "legacy-mined",
    visible: minedVisible,
    fingerprint: profileFingerprint(minedVisible),
  });
  const edited = legacyBlock({
    key: "legacy-edited",
    visible: editedVisible,
    fingerprint: profileFingerprint(originalEditedVisible),
  });

  await Bun.write(filePath, `${mined}\n\n${edited}\n`);
  await Bun.write(
    paths.profileManifestFile,
    `${relativePath}\tlegacy-mined\n${relativePath}\tlegacy-edited\n`,
  );

  await writeProfile({ paths, rules: [] });

  const rules = parseProfileRules(await Bun.file(filePath).text());
  const migrated = rules.find((rule) => rule.key === "legacy-mined");
  const generated = await readGeneratedProfileState(paths.profileManifestFile);

  expect(await Bun.file(filePath).text()).toContain(edited);
  expect(migrated).toMatchObject({
    title: "Hold the stated scope",
    source: "mined",
    status: "candidate",
    legacy: false,
    observations: 2,
    sessions: 1,
    origins: ["github.com/acme"],
  });
  expect(migrated?.evidence).toEqual({ for: [], against: [] });
  expect(generated).toContainEqual(
    expect.objectContaining({ key: "legacy-mined", disposition: "present" }),
  );
});

test("migrated legacy guidance keeps the standard session activation bar", async () => {
  const paths = await createTestPaths();
  const relativePath = "org/github.com--acme/workflow.md";
  const filePath = path.join(paths.profileDirectory, relativePath);
  const visible = "## Hold the stated scope\n\nReport adjacent findings.";

  await Bun.write(
    filePath,
    `${legacyBlock({ key: "established", visible, fingerprint: profileFingerprint(visible), sessions: 8 })}\n`,
  );
  await Bun.write(paths.profileManifestFile, `${relativePath}\testablished\n`);

  await writeProfile({ paths, rules: [] });

  const [migrated] = parseProfileRules(await Bun.file(filePath).text());

  expect(migrated).toMatchObject({
    key: "established",
    status: "active",
    sessions: 8,
  });
});

test("keeps migrated legacy guidance across a later unrelated write", async () => {
  const paths = await createTestPaths();
  const relativePath = "org/github.com--acme/workflow.md";
  const filePath = path.join(paths.profileDirectory, relativePath);
  const visible =
    "## Hold the stated scope\n\nReport adjacent findings instead of folding them in.";

  await Bun.write(
    filePath,
    `${legacyBlock({ key: "legacy-mined", visible, fingerprint: profileFingerprint(visible) })}\n`,
  );

  await writeProfile({ paths, rules: [] });
  await writeProfile({
    paths,
    rules: [
      profileRule({
        key: "unrelated",
        title: "Run focused checks",
        body: "Run one focused check.",
      }),
    ],
  });

  const rules = parseProfileRules(await Bun.file(filePath).text());

  expect(rules.map((rule) => rule.key)).toContain("legacy-mined");
});
