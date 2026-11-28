import {
  isExplicitProfileEvidence,
  profileEvidenceStatistics,
  type ProfileRule,
} from "@shadowclone/profile";
import { materializeEvidenceIds, unionEvidence } from "./evidence";
import { reconciliationProposal } from "./proposal";
import { learnedRuleLocation, promoteGlobalRule } from "./scope";
import type {
  PromptRule,
  ReconciliationContext,
  ReconciliationExistingRule,
  ReconciliationOutput,
} from "./types";

export function applyExisting(options: {
  readonly result: ReconciliationExistingRule;
  readonly promptRule: PromptRule;
  readonly context: ReconciliationContext;
  readonly explicitTokens: ReadonlySet<string>;
  readonly globalTokens: ReadonlySet<string>;
}): ProfileRule | null {
  const additions = materializeEvidenceIds({
    tokens: options.result.evidenceTokens,
    context: options.context,
    explicitTokens: options.explicitTokens,
  });

  if (additions.length === 0) {
    return null;
  }

  const current = options.promptRule.snapshot.rule;
  const reinforces = options.result.verdict === "reinforces";

  const evidence = {
    for: reinforces
      ? unionEvidence(current.evidence.for, additions)
      : current.evidence.for,
    against: reinforces
      ? current.evidence.against
      : unionEvidence(current.evidence.against, additions),
  };

  const statistics = profileEvidenceStatistics({ rule: current, evidence });

  const status =
    current.source !== "mined"
      ? ("active" as const)
      : options.result.verdict !== "reinforces"
        ? ("stale" as const)
        : evidence.for.some(isExplicitProfileEvidence) ||
            statistics.sessions >= 3
          ? ("active" as const)
          : ("candidate" as const);

  const updated: ProfileRule = {
    ...current,
    ...statistics,
    evidence,
    status,
    proposal: reinforces
      ? current.proposal
      : reconciliationProposal({
          result: options.result,
          promptRule: options.promptRule,
        }),
  };

  return promoteGlobalRule({
    rule: updated,
    tokens: options.result.evidenceTokens,
    context: options.context,
    globalTokens: options.globalTokens,
  });
}

export function emptyMinedRule(options: {
  readonly result: ReconciliationOutput["newRules"][number];
  readonly context: ReconciliationContext;
  readonly evidence: readonly string[];
  readonly globalTokens: ReadonlySet<string>;
}): ProfileRule {
  const [first] = options.context.evidence;

  const key = new Bun.CryptoHasher("sha256")
    .update(
      JSON.stringify({
        origin: options.context.batch.origin.id,
        title: options.result.title,
        body: options.result.body,
        section: options.result.section,
        evidence: options.evidence,
      }),
    )
    .digest("hex")
    .slice(0, 24);

  const location = learnedRuleLocation({
    text: `${options.result.title}\n${options.result.body}`,
    tokens: options.result.evidenceTokens,
    context: options.context,
    globalTokens: options.globalTokens,
  });

  const base: ProfileRule = {
    key: `mined:${key}`,
    title: options.result.title,
    body: options.result.body,
    section: options.result.section,
    ...location,
    source: "mined",
    status: "candidate",
    proposal: null,
    appliesWhen: [],
    evidence: { for: options.evidence, against: [] },
    observations: 0,
    sessions: 0,
    origins: first ? [first.signal.origin.id] : [],
    lastSeen: "unknown",
    importReference: null,
  };

  const statistics = profileEvidenceStatistics({
    rule: base,
    evidence: base.evidence,
  });

  return {
    ...base,
    ...statistics,
    status:
      options.evidence.some(isExplicitProfileEvidence) ||
      statistics.sessions >= 3
        ? "active"
        : "candidate",
  };
}
