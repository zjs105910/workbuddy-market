import { expect, test } from "bun:test";
import { mkdir, mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { createProjectPaths } from "@shadowclone/core";
import { profileEvidenceId, renderProfileRule, type ProfileRule } from "@shadowclone/profile";
import type { CorrectionSignal, OriginScope } from "@shadowclone/sessions";
import type { SeedLibrary } from "@shadowclone/skills";
import type { DistillBatch } from "../batch";
import { createReconciliationContext } from "./context";
import { buildReconciliationPrompt } from "./prompt";
import { materializeEvidence } from "../excerpts";
import { readProfileSnapshot } from "@shadowclone/environment";

const profileSecret = ["sk", "proj", "profileSecret123456789"].join("-");
const evidenceSecret = ["sk", "proj", "evidenceSecret123456789"].join("-");
const origin: OriginScope = {
  id: "github.com/private-owner",
  directoryName: "github.com--private-owner--c48a251dc59a4aa3",
  promotable: true,
};

const emptyLibrary: SeedLibrary = {
  guidance: [],
  preferences: [],
  skills: [],
  axes: [],
  independentSkills: [],
};

function declaredRule(): ProfileRule {
  return {
    key: "seed:private-choice",
    title: "Protect credentials",
    body: `Never expose ${profileSecret}.`,
    section: "boundaries",
    scope: "global",
    originDirectory: null,
    repositoryName: null,
    source: "declared",
    status: "active",
    proposal: null,
    appliesWhen: [`credentials such as ${profileSecret} are present`],
    evidence: { for: [], against: [] },
    observations: 0,
    sessions: 0,
    origins: [],
    lastSeen: "declared",
    importReference: null,
  };
}

test("sends only redacted profile text and opaque local tokens", async () => {
  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-prompt-"),
  );
  const paths = createProjectPaths({ homeDirectory, platform: "darwin" });
  const profilePath = path.join(
    paths.profileDirectory,
    "global",
    "boundaries.md",
  );

  await mkdir(path.dirname(profilePath), { recursive: true });
  await Bun.write(profilePath, `${renderProfileRule(declaredRule())}\n`);
  await Bun.write(
    paths.rejectedProfileFile,
    `${JSON.stringify({
      schema: 1,
      relativePath:
        "org/github.com--private-owner--c48a251dc59a4aa3/projects/sample-app--0123456789abcdef.md",
      key: "rejected-private-key",
      title: "Rejected secret",
      body: `Do not restore ${profileSecret}.`,
      source: "imported",
      importReference: {
        repositoryAliases: [
          "1111111111111111111111111111111111111111111111111111111111111111",
        ],
        sourceLocator:
          "2222222222222222222222222222222222222222222222222222222222222222",
      },
      reason: "repo-covered",
    })}\n`,
  );

  const evidencePath = path.join(homeDirectory, "evidence.txt");

  await Bun.write(evidencePath, `The user removed ${evidenceSecret}.`);

  const signal: CorrectionSignal = {
    kind: "interruption",
    category: "tool:Edit",
    label: "while using Edit",
    sessionId: "private-session",
    timestamp: 1_788_537_600_000,
    origin,
    repositoryName: "sample-app--0123456789abcdef",
    textRefs: [
      {
        type: "file",
        sourcePath: evidencePath,
        byteOffset: 0,
        byteLength: Bun.file(evidencePath).size,
      },
    ],
  };

  const profile = await readProfileSnapshot(paths);
  const batch: DistillBatch = {
    origin,
    repositoryName: signal.repositoryName,
    signals: [signal],
  };
  const context = createReconciliationContext({
    batch,
    profile,
    library: emptyLibrary,
  });
  const { excerpts } = await materializeEvidence({ signals: [signal] });
  const prompt = await buildReconciliationPrompt({ context, excerpts });

  const durableEvidenceId = profileEvidenceId({
    originId: origin.id,
    sessionId: signal.sessionId,
    timestamp: signal.timestamp,
    kind: signal.kind,
    category: signal.category,
  });

  expect(profile.rules[0]?.rule.body).toContain(profileSecret);
  expect(profile.rules[0]?.promptAppliesWhen.join(" ")).not.toContain(
    profileSecret,
  );
  expect(prompt).toContain("rule-1");
  expect(prompt).toContain("rejection-1");
  expect(prompt).toContain("evidence-1");
  expect(prompt).toContain("[redacted:llm-api-key]");
  expect(prompt).not.toContain(profileSecret);
  expect(prompt).not.toContain(evidenceSecret);
  expect(prompt).not.toContain(declaredRule().key);
  expect(prompt).not.toContain("rejected-private-key");
  expect(prompt).not.toContain(origin.id);
  expect(prompt).not.toContain(evidencePath);
  expect(prompt).not.toContain(durableEvidenceId);
});
