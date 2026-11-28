import type { DiffFile } from "../collect";
import { isGeneratedPath } from "../generated";
import { matchCredential } from "./credentials";
import type { BuiltInRule, RuleHit } from "./types";

const maximumLineLength = 2_000;
const maximumHitsPerRuleAndFile = 5;
const maximumHits = 100;

function credentialHit(options: {
  readonly text: string;
  readonly path: string;
  readonly line: number;
}): RuleHit | null {
  const credential = matchCredential(options.text);

  if (credential === null) {
    return null;
  }

  return {
    ruleId: `credential-${credential.label}`,
    level: credential.level,
    severity: "high",
    category: "security",
    title: credential.level === "certain" ? "Credential committed" : "Possible credential committed",
    failure: "Anyone who can read the repository or its history can use this credential. Rotate it and load it from a secret store.",
    path: options.path,
    line: options.line,
  };
}

export function findRuleHits(options: {
  readonly files: readonly DiffFile[];
  readonly rules: readonly BuiltInRule[];
}): readonly RuleHit[] {
  const hits: RuleHit[] = [];

  for (const file of options.files) {
    if (file.deleted || isGeneratedPath(file.path)) {
      continue;
    }

    const rules = options.rules.filter((rule) => rule.files.test(file.path));
    const countsByRule = new Map<string, number>();
    const record = (hit: RuleHit): void => {
      const count = countsByRule.get(hit.ruleId) ?? 0;

      if (count < maximumHitsPerRuleAndFile) {
        countsByRule.set(hit.ruleId, count + 1);
        hits.push(hit);
      }
    };

    for (const added of file.added) {
      if (added.text.length > maximumLineLength) {
        continue;
      }

      for (const rule of rules.filter((candidate) => candidate.pattern.test(added.text))) {
        record({
          ruleId: rule.id,
          level: rule.level,
          severity: rule.severity,
          category: rule.category,
          title: rule.title,
          failure: rule.failure,
          path: file.path,
          line: added.line,
        });
      }

      const credential = credentialHit({ text: added.text, path: file.path, line: added.line });

      if (credential) {
        record(credential);
      }
    }
  }

  return hits.slice(0, maximumHits);
}
