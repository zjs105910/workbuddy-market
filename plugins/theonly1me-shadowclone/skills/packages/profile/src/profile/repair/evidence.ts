import { profileEvidenceStatistics } from "../evidence";
import type { ProfileRule } from "../types";

function rewriteIdentifier(options: {
  readonly identifier: string;
  readonly originId: string;
}): string {
  const explicit = options.identifier.startsWith("explicit:");
  const prefix = explicit ? "explicit:" : "";
  const normalized = explicit
    ? options.identifier.slice(prefix.length)
    : options.identifier;

  if (!normalized.startsWith("signal:")) {
    return options.identifier;
  }

  let value: unknown;

  try {
    value = JSON.parse(normalized.slice("signal:".length));
  } catch {
    return options.identifier;
  }

  if (
    !Array.isArray(value) ||
    value.length !== 5 ||
    typeof value[0] !== "string"
  ) {
    return options.identifier;
  }

  return `${prefix}signal:${JSON.stringify([options.originId, ...value.slice(1)])}`;
}

export function repairRuleEvidence(options: {
  readonly rule: ProfileRule;
  readonly originId: string;
}): ProfileRule {
  const evidence = {
    for: options.rule.evidence.for.map((identifier) =>
      rewriteIdentifier({ identifier, originId: options.originId }),
    ),
    against: options.rule.evidence.against.map((identifier) =>
      rewriteIdentifier({ identifier, originId: options.originId }),
    ),
  };

  const rule = {
    ...options.rule,
    evidence,
    origins: options.rule.origins.length > 0 ? [options.originId] : [],
  };

  return { ...rule, ...profileEvidenceStatistics({ rule, evidence }) };
}
