import { expect, test } from "bun:test";
import type { ProfileRule, ProfileSnapshot } from "@shadowclone/profile";
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

function signal(sessionId: string): CorrectionSignal {
  return {
    kind: "interruption",
    category: "tool:Edit",
    label: "while using Edit",
    sessionId,
    timestamp: 1_788_537_600_000,
    origin,
    repositoryName: "project",
    textRefs: [],
  };
}

function rule(source: ProfileRule["source"]): ProfileRule {
  return {
    key: source === "declared" ? "seed:plan-first" : `${source}-rule`,
    title: "Plan first",
    body: "Present a plan before editing.",
    section: "workflow",
    scope: "global",
    originDirectory: null,
    repositoryName: null,
    source,
    status: "active",
    proposal: null,
    appliesWhen: ["consequential changes"],
    evidence: { for: [], against: [] },
    observations: 0,
    sessions: 0,
    origins: [],
    lastSeen: "declared",
    importReference: null,
  };
}

function profile(profileRule: ProfileRule): ProfileSnapshot {
  return {
    rules: [
      {
        rule: profileRule,
        promptTitle: profileRule.title,
        promptBody: profileRule.body,
        promptAppliesWhen: profileRule.appliesWhen,
        promptProposal: profileRule.proposal,
      },
    ],
    rejections: [],
  };
}

function batch(): DistillBatch {
  return { origin, repositoryName: "project", signals: [signal("session-1")] };
}

const library: SeedLibrary = {
  guidance: [
    {
      id: "plan-first",
      title: "Plan first",
      axis: "planning-style",
      category: "workflow",
      section: "workflow",
      appliesWhen: ["consequential changes"],
      body: "Present a plan before editing.",
      kind: "preference",
    },
    {
      id: "act-first",
      title: "Act first",
      axis: "planning-style",
      category: "workflow",
      section: "workflow",
      appliesWhen: ["small changes"],
      body: "Start small changes immediately.",
      kind: "preference",
    },
  ],
  preferences: [],
  skills: [],
  axes: [],
  independentSkills: [],
};

const axisLibrary: SeedLibrary = {
  ...library,
  axes: [{ id: "planning-style", guidance: library.guidance }],
};

test("keeps declared guidance active and proposes a concrete sibling", () => {
  const context = createReconciliationContext({
    batch: batch(),
    profile: profile(rule("declared")),
    library: axisLibrary,
  });

  const applied = applyReconciliation({
    context,
    output: {
      existingRules: [
        {
          ruleToken: "rule-1",
          verdict: "narrows",
          observed: "Small changes proceed without planning.",
          evidenceTokens: ["evidence-1"],
          proposedTitle: "",
          proposedBody: "",
          axisChoiceToken: ["option", "1"].join("-"),
        },
      ],
      newRules: [],
    },
  });

  expect(applied.rules[0]?.status).toBe("active");
  expect(applied.rules[0]?.proposal).toEqual({
    kind: "narrow",
    text: "Act first\n\nStart small changes immediately.\n\nApplies when: small changes",
  });
  expect(applied.rules[0]?.evidence.against).toHaveLength(1);
  expect(applied.rules[0]?.lastSeen).toBe("2026-09-04");
});

test("keeps authoritative guidance active but marks contradicted mined guidance stale", () => {
  for (const source of ["user", "imported", "mined"] as const) {
    const context = createReconciliationContext({
      batch: batch(),
      profile: profile(rule(source)),
      library: axisLibrary,
    });

    const applied = applyReconciliation({
      context,
      output: {
        existingRules: [
          {
            ruleToken: "rule-1",
            verdict: "contradicts",
            observed: "The user acted directly.",
            evidenceTokens: ["evidence-1"],
            proposedTitle: "Act directly",
            proposedBody: "Start small changes without a plan.",
            axisChoiceToken: "",
          },
        ],
        newRules: [],
      },
    });

    expect(applied.rules[0]?.status).toBe(
      source === "mined" ? "stale" : "active",
    );
    expect(applied.rules[0]?.proposal?.text).toBe(
      "Act directly\n\nStart small changes without a plan.",
    );
  }
});
