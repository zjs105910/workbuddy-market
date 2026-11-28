import { existsSync } from "node:fs";
import { readEffectiveConfig } from "@shadowclone/core";
import { authorizedLearningEvents, currentEvidenceAuthorization } from "../distill";
import { materializeEvidence } from "../distill/excerpts";
import {
  pendingLearningRecords,
  readEnvironment,
  readRedactedEnvironment,
} from "@shadowclone/environment";
import { openEventIndex, textRefKey, captureRoots, deriveSignals } from "@shadowclone/sessions";
import type { ProjectPaths } from "@shadowclone/core";
import { parseProfileEvidenceId, type ProfileRule } from "@shadowclone/profile";
import { redactSecrets } from "@shadowclone/redact";
import { listSkillProposals } from "@shadowclone/skills";
import { readPendingLearning } from "./pending";
import { correctionReviewSignals } from "./feedback";
import { readLatestProbe } from "./probe";

export async function learningCatalog(options: {
  readonly paths: ProjectPaths;
  readonly pendingOnly?: boolean;
}) {
  const [pending, state, proposals, signals] = await Promise.all([
    readPendingLearning(options.paths),
    readRedactedEnvironment(options.paths),
    listSkillProposals(options.paths),
    correctionReviewSignals(options.paths),
  ]);
  const blockers = state ? pendingLearningRecords({ paths: options.paths, state }) : [];
  const learning = pending.rules.map((rule) => ({
    kind: "learning" as const,
    key: rule.key,
    title: redactSecrets({ text: rule.title }),
    scope: rule.scope,
    status: "awaiting-review",
    reason: "Approve or reject this learned rule.",
  }));
  const stored = state?.records.filter(({ rule }) =>
    !pending.rules.some((entry) => entry.key === rule.key),
  ).flatMap((record) => {
    const unresolved = blockers.filter((entry) => entry.key === record.rule.key);
    if (unresolved.length > 0) return unresolved;
    const feedback = signals.find((entry) => entry.key === record.rule.key);
    if (feedback && !record.retirementRequested) return [{
      kind: "learning" as const, key: record.rule.key, title: record.rule.title,
      scope: record.rule.scope, status: "needs-behavior-review", reason: feedback.reason,
      correctionCount: feedback.count,
    }];
    if (options.pendingOnly) return [];
    return [{
      kind: "learning" as const,
      key: record.rule.key,
      title: record.rule.title,
      scope: record.rule.scope,
      status: record.retirementRequested ? "retired" : "active",
      reason: record.retirementRequested ? "Retirement was explicitly requested." : "Guidance is published or covered.",
    }];
  }) ?? [];

  return [
    ...learning,
    ...stored,
    ...proposals.filter((proposal) => proposal.status === "pending").map((proposal) => ({
      kind: "skill" as const,
      key: proposal.id,
      title: "Skill change needs review",
      scope: "skill-library",
      status: "awaiting-review",
      reason: "Run shadowclone learning show with this key to inspect the proposed change.",
    })),
  ];
}

async function supportingExcerpts(options: {
  readonly paths: ProjectPaths;
  readonly rule: ProfileRule;
}): Promise<readonly string[]> {
  if (!existsSync(options.paths.indexDatabase)) return [];
  const { config } = await readEffectiveConfig({
    configPath: options.paths.configFile,
    managedConfigPath: options.paths.managedConfigFile,
  });
  const index = await openEventIndex(options.paths.indexDatabase);

  try {
    const events = authorizedLearningEvents({ events: index.listEvents(), config });
    const derived = await deriveSignals({
      events, corpus: index.getCorpusSummary(), gitMetadataEnabled: false,
    });
    const moments = options.rule.evidence.for.flatMap((identifier) => {
      const moment = parseProfileEvidenceId(identifier);
      return moment ? [moment] : [];
    });
    const signals = derived.learning.filter((signal) => moments.some((moment) =>
      signal.sessionId === moment.sessionId && signal.timestamp === moment.timestamp,
    )).slice(-5);
    const evidence = await materializeEvidence({
      signals,
      sourceRoots: captureRoots(options.paths),
      requireSteeringCue: false,
      authorizeRef: currentEvidenceAuthorization({ paths: options.paths, events }),
    });
    return evidence.signals.flatMap((signal) => signal.textRefs.flatMap((ref) => {
      const excerpt = evidence.excerpts.get(textRefKey(ref));
      return excerpt ? [excerpt.slice(0, 4_000)] : [];
    })).slice(-5);
  } finally {
    index.close();
  }
}

export async function showLearning(options: {
  readonly paths: ProjectPaths;
  readonly key: string;
}) {
  const pending = await readPendingLearning(options.paths);
  const state = await readEnvironment(options.paths);
  const record = state?.records.find(({ rule }) => rule.key === options.key);
  const rule = pending.rules.find((entry) => entry.key === options.key) ?? record?.rule;
  if (!rule) throw new Error("Learned rule was not found");
  const entries = await learningCatalog({ paths: options.paths });
  const probe = await readLatestProbe(options.paths);

  return {
    key: rule.key,
    title: redactSecrets({ text: rule.title }),
    guidance: redactSecrets({ text: rule.body }),
    proposedChange: rule.proposal === null ? null : {
      kind: rule.proposal.kind,
      guidance: redactSecrets({ text: rule.proposal.text }),
    },
    scope: {
      kind: rule.scope,
      origin: rule.originDirectory,
      repository: rule.repositoryName,
    },
    appliesWhen: rule.appliesWhen.map((text) => redactSecrets({ text })),
    sources: pending.provenance[rule.key]?.sources ?? record?.captureSources ?? [],
    evidence: await supportingExcerpts({ ...options, rule }),
    delivery: entries.filter((entry) => entry.key === rule.key),
    latestProbe: probe?.key === rule.key ? probe : null,
    laterCorrections: (await correctionReviewSignals(options.paths)).find((entry) => entry.key === rule.key) ?? null,
  };
}
