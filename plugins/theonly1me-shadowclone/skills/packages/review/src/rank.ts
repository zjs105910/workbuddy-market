import type { Finding } from "./types";

export const maximumFindings = 10;

const severityOrder: Readonly<Record<Finding["severity"], number>> = {
  high: 0,
  medium: 1,
  low: 2,
};

const categoryOrder: Readonly<Record<Finding["category"], number>> = {
  security: 0,
  correctness: 1,
  performance: 2,
  tests: 3,
  standards: 4,
};

const nearbyLineDistance = 3;

function isDuplicate(options: { readonly kept: readonly Finding[]; readonly finding: Finding }): boolean {
  return options.kept.some(
    (existing) =>
      existing.path === options.finding.path &&
      existing.category === options.finding.category &&
      Math.abs(existing.line - options.finding.line) <= nearbyLineDistance,
  );
}

export function rankFindings(findings: readonly Finding[]): readonly Finding[] {
  const sorted = [...findings].sort(
    (left, right) =>
      severityOrder[left.severity] - severityOrder[right.severity] ||
      categoryOrder[left.category] - categoryOrder[right.category] ||
      left.path.localeCompare(right.path) ||
      left.line - right.line,
  );
  const kept: Finding[] = [];

  for (const finding of sorted) {
    if (!isDuplicate({ kept, finding })) {
      kept.push(finding);
    }
  }

  return kept.slice(0, maximumFindings);
}
