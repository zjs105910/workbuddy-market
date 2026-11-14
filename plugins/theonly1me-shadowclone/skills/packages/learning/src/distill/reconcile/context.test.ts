import { expect, test } from "bun:test";
import type { ProfileRule, ProfileSnapshotRule } from "@shadowclone/profile";
import type { CorrectionSignal, OriginScope } from "@shadowclone/sessions";
import type { SeedLibrary } from "@shadowclone/skills";
import type { DistillBatch } from "../batch";
import { createReconciliationContext } from "./context";

const origin: OriginScope = {
  id: "github.com/acme",
  directoryName: "github.com--acme--936913df4a5c268b",
  promotable: true,
};

const library: SeedLibrary = {
  guidance: [],
  preferences: [],
  skills: [],
  axes: [],
  independentSkills: [],
};

function snapshot(rule: ProfileRule): ProfileSnapshotRule {
  return {
    rule,
    promptTitle: rule.title,
    promptBody: rule.body,
    promptAppliesWhen: rule.appliesWhen,
    promptProposal: rule.proposal,
  };
}

function fields(key: string) {
  return {
    key,
    title: key,
    body: `${key} body`,
    section: "engineering" as const,
    source: "imported" as const,
    status: "active" as const,
    proposal: null,
    appliesWhen: [],
    evidence: { for: [], against: [] },
    observations: 0,
    sessions: 0,
    origins: [],
    lastSeen: "imported",
    importReference: null,
  };
}

test("scopes project guidance to the exact repository", () => {
  const signal: CorrectionSignal = {
    kind: "interruption",
    category: "tool:Edit",
    label: "while using Edit",
    sessionId: "session",
    timestamp: 1,
    origin,
    repositoryName: "target",
    textRefs: [],
  };

  const batch: DistillBatch = {
    origin,
    repositoryName: "target",
    signals: [signal],
  };

  const rules: ProfileSnapshotRule[] = [
    snapshot({
      ...fields("global"),
      scope: "global",
      originDirectory: null,
      repositoryName: null,
    }),
    snapshot({
      ...fields("organization"),
      scope: "org",
      originDirectory: origin.directoryName,
      repositoryName: null,
    }),
    snapshot({
      ...fields("target"),
      scope: "project",
      originDirectory: origin.directoryName,
      repositoryName: "target",
    }),
    snapshot({
      ...fields("sibling"),
      scope: "project",
      originDirectory: origin.directoryName,
      repositoryName: "sibling",
    }),
  ];

  const context = createReconciliationContext({
    batch,
    profile: { rules, rejections: [] },
    library,
  });

  expect(context.rules.map((entry) => entry.snapshot.rule.key)).toEqual([
    "global",
    "organization",
    "target",
  ]);
});
