import { expect, test } from "bun:test";
import {
  profileEvidenceId,
  type ProfileRule,
  type ProfileSnapshot,
} from "@shadowclone/profile";
import type { CorrectionSignal, OriginScope } from "@shadowclone/sessions";
import type { SeedLibrary } from "@shadowclone/skills";
import type { DistillBatch } from "../batch";
import { applyReconciliation } from "./apply";
import { createReconciliationContext } from "./context";

const origin: OriginScope = {
  id: "github.com/acme",
  directoryName: "github.com--acme--936913df4a5c268b",
  promotable: true,
};

const emptyLibrary: SeedLibrary = {
  guidance: [],
  preferences: [],
  skills: [],
  axes: [],
  independentSkills: [],
};

function signal(sessionIndex: number): CorrectionSignal {
  return {
    kind: "question-answered",
    category: "agent-question",
    label: "an agent question",
    sessionId: `session-${sessionIndex}`,
    timestamp: 1_788_537_600_000 + sessionIndex,
    origin,
    repositoryName: null,
    textRefs: [],
  };
}

function context(
  sessionCount: number,
  profile: ProfileSnapshot = { rules: [], rejections: [] },
) {
  const batch: DistillBatch = {
    origin,
    repositoryName: null,
    signals: Array.from({ length: sessionCount }, (_, index) =>
      signal(index + 1),
    ),
  };

  return createReconciliationContext({ batch, profile, library: emptyLibrary });
}

function newRule(evidenceTokens: readonly string[], rejectionToken = "") {
  return {
    title: "Prefer the smaller scope",
    body: "Choose the smallest change that satisfies the request.",
    section: "workflow" as const,
    observed: "The user repeatedly selected the smaller option.",
    evidenceTokens,
    rejectionToken,
  };
}

test("activates mined guidance only after three independent sessions", () => {
  const candidate = applyReconciliation({
    context: context(2),
    output: {
      existingRules: [],
      newRules: [newRule(["evidence-1", "evidence-2", "evidence-unknown"])],
    },
  });

  const active = applyReconciliation({
    context: context(3),
    output: {
      existingRules: [],
      newRules: [newRule(["evidence-1", "evidence-2", "evidence-3"])],
    },
  });

  expect(candidate.rules[0]?.status).toBe("candidate");
  expect(candidate.rules[0]?.evidence.for).toHaveLength(2);
  expect(active.rules[0]?.status).toBe("active");
  expect(active.rules[0]?.sessions).toBe(3);
});

test("unions rule-specific reinforcement with prior evidence", () => {
  const priorEvidence = profileEvidenceId({
    originId: origin.id,
    sessionId: "session-prior",
    timestamp: 1_788_537_500_000,
    kind: "question-answered",
    category: "agent-question",
  });

  const existing: ProfileRule = {
    key: "mined-existing",
    title: "Prefer the smaller scope",
    body: "Choose the smallest change that satisfies the request.",
    section: "workflow",
    scope: "org",
    originDirectory: origin.directoryName,
    repositoryName: null,
    source: "mined",
    status: "candidate",
    proposal: null,
    appliesWhen: [],
    evidence: { for: [priorEvidence], against: [] },
    observations: 1,
    sessions: 1,
    origins: [origin.id],
    lastSeen: "2026-09-05",
    importReference: null,
  };

  const profile: ProfileSnapshot = {
    rules: [
      {
        rule: existing,
        promptTitle: existing.title,
        promptBody: existing.body,
        promptAppliesWhen: existing.appliesWhen,
        promptProposal: existing.proposal,
      },
    ],
    rejections: [],
  };

  const applied = applyReconciliation({
    context: context(2, profile),
    output: {
      existingRules: [
        {
          ruleToken: "rule-1",
          verdict: "reinforces",
          observed: "Two more sessions chose the smaller scope.",
          evidenceTokens: ["evidence-1", "evidence-2", "evidence-unknown"],
          proposedTitle: "",
          proposedBody: "",
          axisChoiceToken: "",
        },
      ],
      newRules: [],
    },
  });

  expect(applied.rules[0]?.evidence.for).toHaveLength(3);
  expect(applied.rules[0]?.sessions).toBe(3);
  expect(applied.rules[0]?.status).toBe("active");
});

test("omits a semantic match to rejected guidance", () => {
  const rejectedProfile: ProfileSnapshot = {
    rules: [],
    rejections: [
      {
        rejection: {
          relativePath: "global/workflow.md",
          key: "rejected-key",
          title: "Keep changes small",
          body: "Always minimize the change.",
          source: "mined",
          importReference: null,
        },
        promptTitle: "Keep changes small",
        promptBody: "Always minimize the change.",
      },
    ],
  };

  const applied = applyReconciliation({
    context: context(1, rejectedProfile),
    output: {
      existingRules: [],
      newRules: [newRule(["evidence-1"], "rejection-1")],
    },
  });

  expect(applied.rules).toEqual([]);
  expect(applied.rejectedMatches).toBe(1);
});
