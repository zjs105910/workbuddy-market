import { armNames } from "./arms";
import { bootstrapInterval, detectedIds, finalLabels, type judgedCaseSchema } from "./analyze";
import type { RunSummary } from "./collect";
import type { z } from "zod";

type JudgedCase = z.infer<typeof judgedCaseSchema>;

export type ArmMetrics = {
  readonly arm: string;
  readonly completed: number;
  readonly cases: number;
  readonly findings: number;
  readonly real: number;
  readonly minor: number;
  readonly wrong: number;
  readonly disputed: number;
  readonly wrongRate: number | null;
  readonly wrongInterval: readonly [number, number] | null;
  readonly realShare: number | null;
  readonly realInterval: readonly [number, number] | null;
  readonly detected: number;
  readonly defectCases: number;
  readonly findingsPerCleanCase: number | null;
  readonly medianSeconds: number | null;
};

function median(values: readonly number[]): number | null {
  const sorted = [...values].sort((left, right) => left - right);

  return sorted.length === 0 ? null : (sorted[Math.floor((sorted.length - 1) / 2)] ?? null);
}

export function armMetrics(options: {
  readonly judged: readonly JudgedCase[];
  readonly summaries: readonly RunSummary[];
  readonly tiebreaks: ReadonlyMap<string, string>;
  readonly seed: number;
}): readonly ArmMetrics[] {
  const reported = armNames.filter((arm) => options.summaries.some((summary) => summary.arm === arm));

  return reported.map((arm, armIndex) => {
    const runs = options.summaries.filter((summary) => summary.arm === arm);
    const completedCases = new Set(runs.filter((summary) => summary.done).map((summary) => summary.caseId));
    const perCase = options.judged
      .filter((judged) => completedCases.has(judged.caseId))
      .map((judged) => {
        const labels = finalLabels({ judged, tiebreaks: options.tiebreaks });
        const mine = judged.findings.filter((finding) => finding.arm === arm);
        const count = (label: string) => mine.filter((finding) => labels.get(finding.id) === label).length;
        const detected = detectedIds(judged);

        return {
          kind: judged.kind,
          total: mine.length,
          real: count("real"),
          minor: count("minor"),
          wrong: count("wrong"),
          disputed: count("disputed"),
          detected: mine.some((finding) => detected.has(finding.id)),
        };
      });
    const sum = (pick: (entry: (typeof perCase)[number]) => number) => perCase.reduce((total, entry) => total + pick(entry), 0);
    const decided = sum((entry) => entry.real + entry.minor + entry.wrong);
    const clean = perCase.filter((entry) => entry.kind === "clean");
    const defects = perCase.filter((entry) => entry.kind === "defect");

    return {
      arm,
      completed: completedCases.size,
      cases: runs.length,
      findings: sum((entry) => entry.total),
      real: sum((entry) => entry.real),
      minor: sum((entry) => entry.minor),
      wrong: sum((entry) => entry.wrong),
      disputed: sum((entry) => entry.disputed),
      wrongRate: decided === 0 ? null : sum((entry) => entry.wrong) / decided,
      wrongInterval: bootstrapInterval({ cases: perCase.map((entry) => ({ numerator: entry.wrong, denominator: entry.real + entry.minor + entry.wrong })), seed: options.seed + armIndex }),
      realShare: decided === 0 ? null : sum((entry) => entry.real) / decided,
      realInterval: bootstrapInterval({ cases: perCase.map((entry) => ({ numerator: entry.real, denominator: entry.real + entry.minor + entry.wrong })), seed: options.seed + 10 + armIndex }),
      detected: defects.filter((entry) => entry.detected).length,
      defectCases: defects.length,
      findingsPerCleanCase: clean.length === 0 ? null : clean.reduce((total, entry) => total + entry.total, 0) / clean.length,
      medianSeconds: median(runs.flatMap((summary) => (summary.seconds === null ? [] : [summary.seconds]))),
    };
  });
}

function percent(value: number | null): string {
  return value === null ? "n/a" : `${Math.round(value * 100)}%`;
}

function interval(value: readonly [number, number] | null): string {
  return value === null ? "" : ` (${percent(value[0])} to ${percent(value[1])})`;
}

export function metricsTable(metrics: readonly ArmMetrics[]): string {
  const rows = metrics.map(
    (entry) =>
      `| ${entry.arm} | ${entry.completed} of ${entry.cases} | ${entry.findings} | ${percent(entry.realShare)}${interval(entry.realInterval)} | ${percent(entry.wrongRate)}${interval(entry.wrongInterval)} | ${entry.detected} of ${entry.defectCases} | ${entry.findingsPerCleanCase?.toFixed(1) ?? "n/a"} | ${entry.medianSeconds ?? "n/a"} s |`,
  );

  return [
    "| Reviewer | Reviews done | Findings | Real | Wrong | Known bugs found | Findings per clean PR | Median time |",
    "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ...rows,
  ].join("\n");
}
