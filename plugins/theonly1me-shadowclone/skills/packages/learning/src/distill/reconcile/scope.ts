import { explicitProfileEvidence, type ProfileRule } from "@shadowclone/profile";
import type { PromptRule, ReconciliationContext } from "./types";

type RuleLocation =
  | {
      readonly scope: "global";
      readonly originDirectory: null;
      readonly repositoryName: null;
    }
  | {
      readonly scope: "org";
      readonly originDirectory: string;
      readonly repositoryName: null;
    }
  | {
      readonly scope: "project";
      readonly originDirectory: string;
      readonly repositoryName: string;
    };

const repositoryPhrase = /\b(?:this|the|our|that) (?:repository|repo|codebase|project|monorepo)\b|\bin (?:this|the) (?:repository|repo)\b/i;
const repositoryPath = /(?:[\w@.-]+\/){2,}|\b[\w@-]+\/[\w@-]+\.[a-z0-9]{1,5}\b/i;

export function repositoryBound(text: string): boolean {
  const withoutExternalPaths = text.replace(/https?:\/\/\S+|~\/\S+/g, "");
  return repositoryPhrase.test(text) || repositoryPath.test(withoutExternalPaths);
}

function usesGlobalScope(options: {
  readonly tokens: readonly string[];
  readonly context: ReconciliationContext;
  readonly globalTokens: ReadonlySet<string>;
}): boolean {
  const allowed = new Set(options.context.evidence.map((entry) => entry.token));
  const selected = [
    ...new Set(options.tokens.filter((token) => allowed.has(token))),
  ];

  return (
    selected.length > 0 &&
    selected.every((token) => options.globalTokens.has(token))
  );
}

export function learnedRuleLocation(options: {
  readonly tokens: readonly string[];
  readonly context: ReconciliationContext;
  readonly globalTokens: ReadonlySet<string>;
  readonly text: string;
}): RuleLocation {
  if (usesGlobalScope(options) && !repositoryBound(options.text)) {
    return {
      scope: "global",
      originDirectory: null,
      repositoryName: null,
    };
  }

  const repositoryName = options.context.batch.repositoryName;

  return repositoryName === null
    ? {
        scope: "org",
        originDirectory: options.context.batch.origin.directoryName,
        repositoryName: null,
      }
    : {
        scope: "project",
        originDirectory: options.context.batch.origin.directoryName,
        repositoryName,
      };
}

export function promoteGlobalRule(options: {
  readonly rule: ProfileRule;
  readonly tokens: readonly string[];
  readonly context: ReconciliationContext;
  readonly globalTokens: ReadonlySet<string>;
}): ProfileRule {
  if (
    options.rule.source !== "mined" ||
    options.rule.scope === "global" ||
    !usesGlobalScope(options) ||
    repositoryBound(`${options.rule.title}\n${options.rule.body}`)
  ) {
    return options.rule;
  }

  return {
    ...options.rule,
    scope: "global",
    originDirectory: null,
    repositoryName: null,
  };
}

export function promoteRuleFromAssessedEvidence(options: {
  readonly rule: ProfileRule;
  readonly context: ReconciliationContext;
  readonly globalTokens: ReadonlySet<string>;
}): ProfileRule {
  const tokens = options.context.evidence.flatMap((entry) =>
    options.globalTokens.has(entry.token) &&
    options.rule.evidence.for.includes(
      explicitProfileEvidence(entry.evidenceId),
    )
      ? [entry.token]
      : [],
  );

  return promoteGlobalRule({ ...options, tokens });
}

export function assessedScopePromotions(options: {
  readonly rules: readonly PromptRule[];
  readonly context: ReconciliationContext;
  readonly globalTokens: ReadonlySet<string>;
  readonly excludedKeys: ReadonlySet<string>;
}): readonly { readonly before: ProfileRule; readonly after: ProfileRule }[] {
  return options.rules.flatMap((promptRule) => {
    const before = promptRule.snapshot.rule;

    if (options.excludedKeys.has(before.key)) {
      return [];
    }

    const after = promoteRuleFromAssessedEvidence({
      rule: before,
      context: options.context,
      globalTokens: options.globalTokens,
    });

    return after === before ? [] : [{ before, after }];
  });
}
