import { expect, test } from "bun:test";
import { mkdir, mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { createProjectPaths } from "@shadowclone/core";
import { parseReference } from "@shadowclone/profile";
import { parseProfileRules } from "@shadowclone/profile";
import { renderProfileRule } from "@shadowclone/profile";
import { readGeneratedProfileState, readProfileRejections } from "@shadowclone/profile";
import { renderGeneratedProfileState } from "@shadowclone/profile";
import type { ProfileRule } from "@shadowclone/profile";
import { applyProfileCuration } from "@shadowclone/profile";
import { createProfileCurationPlan } from "@shadowclone/profile";
import { parseProfileCurationDecisions } from "@shadowclone/profile";
import { undoRevision } from "./undo";

function rule(options: {
  readonly key: string;
  readonly title: string;
  readonly section: ProfileRule["section"];
}): ProfileRule {
  return {
    key: options.key,
    title: options.title,
    body: `Apply ${options.title}.`,
    section: options.section,
    scope: "global",
    originDirectory: null,
    repositoryName: null,
    source: "mined",
    status: "active",
    proposal: null,
    appliesWhen: [],
    evidence: { for: [], against: [] },
    observations: 1,
    lastSeen: "2026-09-19",
    sessions: 1,
    origins: ["github.com/acme"],
    importReference: null,
  };
}

test("curation moves, rejects, converts, and undoes profile rules", async () => {
  const home = await mkdtemp(path.join(os.tmpdir(), "shadowclone-curation-"));
  const paths = createProjectPaths({ homeDirectory: home, platform: "darwin" });
  const moved = rule({
    key: "move-key",
    title: "Move me",
    section: "engineering",
  });
  const rejected = rule({
    key: "reject-key",
    title: "Reject me",
    section: "workflow",
  });
  const referenced = rule({
    key: "reference-key",
    title: "Reference me",
    section: "boundaries",
  });
  const sourceFiles = [moved, rejected, referenced].map((entry) => ({
    relativePath: `global/${entry.section}.md`,
    entry,
  }));

  for (const source of sourceFiles) {
    const filePath = path.join(paths.profileDirectory, source.relativePath);

    await mkdir(path.dirname(filePath), { recursive: true });
    await Bun.write(filePath, `${renderProfileRule(source.entry)}\n`);
  }

  await Bun.write(
    paths.profileManifestFile,
    renderGeneratedProfileState(
      sourceFiles.map((source) => ({
        relativePath: source.relativePath,
        key: source.entry.key,
        title: source.entry.title,
        body: source.entry.body,
        source: source.entry.source,
        importReference: source.entry.importReference,
        disposition: "present",
      })),
    ),
  );

  const decisions = parseProfileCurationDecisions(
    JSON.stringify({
      rules: [
        {
          action: "move",
          key: moved.key,
          section: "engineering",
          location: {
            scope: "project",
            originDirectory: "github.com--acme--1234",
            repositoryName: "app--5678",
          },
        },
        { action: "reject", key: rejected.key, reason: "skill-covered" },
        {
          action: "reference",
          key: referenced.key,
          reason: "duplicate",
          reference: {
            key: "release-checklist",
            title: "Release checklist",
            summary: "Check release notes before tagging a version.",
            tags: ["release", "checklist"],
            updatedAt: "2026-09-19",
            location: {
              scope: "project",
              originDirectory: "github.com--acme--1234",
              repositoryName: "app--5678",
            },
          },
        },
      ],
    }),
  );

  const plan = await createProfileCurationPlan({ paths, decisions });

  expect({
    moves: plan.moves,
    rejections: plan.rejections,
    references: plan.references,
  }).toEqual({ moves: 1, rejections: 1, references: 1 });

  const result = await applyProfileCuration({ paths, plan });

  if (result.revisionId === null) {
    throw new Error("Curation must create a revision");
  }

  const projectPath = path.join(
    paths.profileDirectory,
    "org/github.com--acme--1234/projects/app--5678.md",
  );

  expect(
    parseProfileRules(await Bun.file(projectPath).text()).map(
      (entry) => entry.key,
    ),
  ).toEqual([moved.key]);
  expect(
    (await readProfileRejections(paths.rejectedProfileFile)).map(
      (entry) => entry.reason,
    ),
  ).toEqual(["duplicate", "skill-covered"]);
  expect(
    (await readGeneratedProfileState(paths.profileManifestFile)).map(
      (entry) => ({
        key: entry.key,
        relativePath: entry.relativePath,
      }),
    ),
  ).toEqual([
    {
      key: moved.key,
      relativePath: "org/github.com--acme--1234/projects/app--5678.md",
    },
  ]);

  const referencePath = path.join(
    paths.profileDirectory,
    "references/org/github.com--acme--1234/projects/app--5678/release-checklist.md",
  );

  expect(parseReference(await Bun.file(referencePath).text())?.body).toBe(
    referenced.body,
  );

  await undoRevision({ paths, id: result.revisionId });

  expect(await Bun.file(projectPath).exists()).toBeFalse();
  expect(await Bun.file(referencePath).exists()).toBeFalse();
  expect(await readProfileRejections(paths.rejectedProfileFile)).toEqual([]);
});

test("curation decisions reject duplicate rule keys", () => {
  const decisions = JSON.stringify({
    rules: [
      { action: "reject", key: "same", reason: "duplicate" },
      { action: "reject", key: "same", reason: "stale" },
    ],
  });

  expect(() => parseProfileCurationDecisions(decisions)).toThrow(
    "duplicate rule keys",
  );
});
