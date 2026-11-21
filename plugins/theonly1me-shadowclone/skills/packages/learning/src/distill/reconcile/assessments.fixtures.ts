import type { ProfileRule } from "@shadowclone/profile";
import { createReconciliationContext } from "./context";
import type { ReconciliationOutput } from "./types";

export const origin = {
  id: "local",
  directoryName: "local",
  promotable: false,
};

export const context = createReconciliationContext({
  batch: {
    origin,
    repositoryName: "current",
    signals: [1, 2, 3].map((session) => ({
      kind: "user-steering" as const,
      origin,
      category: "user-episode",
      label: "user episode",
      timestamp: session,
      sessionId: `session-${session}`,
      repositoryName: "current",
      textRefs: [],
    })),
  },
  profile: { rules: [], rejections: [] },
  library: {
    guidance: [],
    preferences: [],
    skills: [],
    axes: [],
    independentSkills: [],
  },
});

export const newRule = {
  title: "Use complete names",
  body: "Use complete variable names.",
  section: "engineering" as const,
  observed: "Repeated user preference",
  evidenceTokens: ["evidence-1", "evidence-2", "evidence-3"],
  rejectionToken: "",
};

export type Intent = NonNullable<
  ReconciliationOutput["assessments"]
>[number]["intent"];

export function storedRule(evidence: readonly string[] = []): ProfileRule {
  return {
    key: "existing-rule",
    title: newRule.title,
    body: newRule.body,
    section: newRule.section,
    scope: "project",
    originDirectory: origin.directoryName,
    repositoryName: "current",
    source: "mined",
    status: "candidate",
    proposal: null,
    appliesWhen: [],
    evidence: { for: evidence, against: [] },
    observations: evidence.length,
    sessions: evidence.length,
    origins: evidence.length > 0 ? [origin.id] : [],
    lastSeen: evidence.length > 0 ? "1970-01-01" : "unknown",
    importReference: null,
  };
}

export function contextWithRule(rule: ProfileRule) {
  return createReconciliationContext({
    batch: context.batch,
    profile: {
      rules: [
        {
          rule,
          promptTitle: rule.title,
          promptBody: rule.body,
          promptAppliesWhen: [],
          promptProposal: null,
        },
      ],
      rejections: [],
    },
    library: {
      guidance: [],
      preferences: [],
      skills: [],
      axes: [],
      independentSkills: [],
    },
  });
}
