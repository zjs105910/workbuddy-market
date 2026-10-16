import { applyExisting, emptyMinedRule } from "./ruleUpdates";
import type { ProfileRule } from "@shadowclone/profile";
import {
  assessedContext,
  explicitEvidenceTokens,
  globalEvidenceTokens,
} from "./assessments";
import { materializeEvidenceIds } from "./evidence";
import { assessedScopePromotions } from "./scope";
import type {
  AppliedReconciliation,
  ReconciliationContext,
  ReconciliationOutput,
} from "./types";

export function applyReconciliation(options: {
  readonly output: ReconciliationOutput;
  readonly context: ReconciliationContext;
}): AppliedReconciliation {
  const explicitTokens = explicitEvidenceTokens(options.output);
  const globalTokens = globalEvidenceTokens(options.output);

  options = { ...options, context: assessedContext(options) };

  const promptRules = new Map(
    options.context.rules.map((entry) => [entry.token, entry]),
  );
  const rules: ProfileRule[] = [];
  const changes: AppliedReconciliation["changes"][number][] = [];

  for (const result of options.output.existingRules) {
    const promptRule = promptRules.get(result.ruleToken);

    if (!promptRule) {
      continue;
    }

    const after = applyExisting({
      result,
      promptRule,
      context: options.context,
      explicitTokens,
      globalTokens,
    });

    if (!after) {
      continue;
    }

    rules.push(after);
    changes.push({
      kind: result.verdict,
      observed: result.observed,
      before: promptRule.snapshot.rule,
      after,
    });
  }

  const updatedKeys = new Set(rules.map((rule) => rule.key));

  for (const { before, after } of assessedScopePromotions({
    rules: options.context.rules,
    context: options.context,
    globalTokens,
    excludedKeys: updatedKeys,
  })) {
    rules.push(after);
    changes.push({
      kind: "scope",
      observed: "The explicit preference applies across repositories.",
      before,
      after,
    });
  }

  const rejectionTokens = new Set(
    options.context.rejections.map((entry) => entry.token),
  );
  let rejectedMatches = 0;

  for (const result of options.output.newRules) {
    if (result.rejectionToken && rejectionTokens.has(result.rejectionToken)) {
      rejectedMatches += 1;

      continue;
    }

    const evidence = materializeEvidenceIds({
      tokens: result.evidenceTokens,
      context: options.context,
      explicitTokens,
    });

    if (evidence.length === 0) {
      continue;
    }

    const after = emptyMinedRule({
      result,
      context: options.context,
      evidence,
      globalTokens,
    });

    rules.push(after);
    changes.push({
      kind: "new",
      observed: result.observed,
      before: null,
      after,
    });
  }

  return { rules, changes, rejectedMatches };
}
