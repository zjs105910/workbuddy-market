import { redactionRules } from "@shadowclone/redact";
import type { RuleLevel } from "./types";

export type CredentialMatch = {
  readonly label: string;
  readonly level: RuleLevel;
};

const certainLabels = [
  "stripe-key",
  "google-api-key",
  "llm-api-key",
  "github-token",
  "slack-token",
  "aws-access-key-id",
] as const;
const signalLabels = ["jwt", "secret-assignment", "database-url"] as const;
const placeholderText = /example|dummy|fake|placeholder|redacted|x{4,}|changeme|your[_-]?(?:api[_-]?)?(?:key|token)/i;
const testModeKey = /^[sr]k_test_/;
const urlWithPassword = /:\/\/[^:/\s]+:[^@\s]+@/;

const credentialPatterns = redactionRules.flatMap((rule) => {
  const certain = certainLabels.some((label) => label === rule.label);
  const signal = signalLabels.some((label) => label === rule.label);

  if (!certain && !signal) {
    return [];
  }

  return [
    {
      label: rule.label,
      level: certain ? ("certain" as const) : ("signal" as const),
      pattern: new RegExp(rule.pattern.source, rule.pattern.flags.replace("g", "")),
    },
  ];
});

export function matchCredential(text: string): CredentialMatch | null {
  if (placeholderText.test(text)) {
    return null;
  }

  for (const candidate of credentialPatterns) {
    const [value] = candidate.pattern.exec(text) ?? [];

    if (value === undefined) {
      continue;
    }

    if (candidate.label === "database-url" && !urlWithPassword.test(value)) {
      continue;
    }

    const level = testModeKey.test(value) ? "signal" : candidate.level;

    return { label: candidate.label, level };
  }

  return null;
}
