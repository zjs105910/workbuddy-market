import type { EngineRunner } from "@shadowclone/agents";
import {
  isExplicitProfileEvidence,
  profileEvidenceStatistics,
  type ProfileEvidence,
  type ProfileRule,
} from "@shadowclone/profile";
import { mergeDistilledRules } from "./merge";

export type DroppedMergeRule = {
  readonly title: string;
  readonly reason: string;
};

type ConsolidatedRules = {
  readonly rules: readonly ProfileRule[];
  readonly dropped: readonly DroppedMergeRule[];
};

function unionEvidence(rules: readonly ProfileRule[]): ProfileEvidence {
  return {
    for: [...new Set(rules.flatMap((rule) => rule.evidence.for))],
    against: [...new Set(rules.flatMap((rule) => rule.evidence.against))],
  };
}

async function consolidateOrigin(options: {
  readonly rules: readonly ProfileRule[];
  readonly runner: EngineRunner;
  readonly workingDirectory: string;
  readonly checkpointDirectory?: string;
}): Promise<ConsolidatedRules> {
  if (options.rules.length <= 1) {
    return { rules: options.rules, dropped: [] };
  }

  const merged = await mergeDistilledRules({
    rules: options.rules.map((rule) => ({
      title: rule.title,
      body: rule.body,
      section: rule.section,
    })),
    runner: options.runner,
    cwd: options.workingDirectory,
    checkpointDirectory: options.checkpointDirectory,
  });

  const rules = merged.rules.flatMap((result, resultIndex) => {
    const sourceIndices = result.sources ?? [resultIndex];
    const constituents = [...new Set(sourceIndices)].flatMap((index) =>
      options.rules[index] ? [options.rules[index]] : [],
    );
    const [first] = constituents;

    if (!first) {
      return [];
    }

    const evidence = unionEvidence(constituents);

    const combined: ProfileRule = {
      ...first,
      title: result.title,
      body: result.body,
      section: result.section,
      evidence,
    };

    const statistics = profileEvidenceStatistics({ rule: combined, evidence });

    return [
      {
        ...combined,
        ...statistics,
        status:
          evidence.for.some(isExplicitProfileEvidence) ||
          statistics.sessions >= 3
            ? ("active" as const)
            : ("candidate" as const),
      },
    ];
  });

  return {
    rules,
    dropped: merged.dropped.map((drop) => ({ title: drop.rule.title, reason: drop.reason })),
  };
}

export async function consolidateNewRules(options: {
  readonly rules: readonly ProfileRule[];
  readonly runner: EngineRunner;
  readonly workingDirectory: string;
  readonly checkpointDirectory?: string;
}): Promise<ConsolidatedRules> {
  const groups = Map.groupBy(options.rules, (rule) => rule.originDirectory);
  const rules: ProfileRule[] = [];
  const dropped: DroppedMergeRule[] = [];

  for (const group of groups.values()) {
    const consolidated = await consolidateOrigin({ ...options, rules: group });

    rules.push(...consolidated.rules);
    dropped.push(...consolidated.dropped);
  }

  return { rules, dropped };
}
