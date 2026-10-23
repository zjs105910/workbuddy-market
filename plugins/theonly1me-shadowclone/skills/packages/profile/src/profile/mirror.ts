import type { MirrorReport } from "@shadowclone/sessions";

function countedLine(options: {
  readonly label: string;
  readonly count: number | string;
}): string {
  const width = Math.max(3, 48 - options.label.length);

  return `    ${options.label} ${".".repeat(width)} ${options.count}`;
}

function ratioLine(options: {
  readonly label: string;
  readonly count: number;
  readonly total: number;
}): string {
  return countedLine({
    label: options.label,
    count: `${options.count} of ${options.total}`,
  });
}

function countLabel(options: {
  readonly count: number;
  readonly singular: string;
  readonly plural: string;
}): string {
  return options.count === 1 ? options.singular : options.plural;
}

function resultLine(options: {
  readonly eligibleSteeringEpisodes: number;
  readonly deepChangesProposed: number | undefined;
  readonly profileUpdated: boolean;
  readonly pendingReview: number;
}): string {
  if (options.deepChangesProposed === undefined) {
    return options.eligibleSteeringEpisodes === 0
      ? "  No user steering episodes are eligible for deep learning."
      : "  Run shadowclone learn --deep to reconcile the eligible moments.";
  }

  if (options.deepChangesProposed === 0) {
    return options.profileUpdated
      ? "  Deep learning found no new rules; existing guidance was updated."
      : "  Deep learning found no new rules.";
  }

  const ruleLabel = countLabel({
    count: options.deepChangesProposed,
    singular: "rule",
    plural: "rules",
  });

  if (!options.profileUpdated) {
    return options.pendingReview > 0
      ? `  Saved ${options.pendingReview} learned ${ruleLabel} for review. Run shadowclone learning pending.`
      : `  Deep learning proposed ${options.deepChangesProposed} ${ruleLabel}; no changes were applied.`;
  }

  return `  Recorded ${options.deepChangesProposed} learned ${ruleLabel}. Check shadowclone learning status for delivery.`;
}

export function renderMirror(options: {
  readonly report: MirrorReport;
  readonly deepLearningPreview: {
    readonly eligibleSteeringEpisodes: number;
    readonly extractionBatches: number;
  };
  readonly networkCallsMade?: boolean;
  readonly deepChangesProposed?: number;
  readonly profileUpdated?: boolean;
  readonly pendingReview?: number;
}): string {
  const report = options.report;
  const megabytes = (report.corpus.bytes / 1_048_576).toFixed(1);
  const corrections = report.correctionCounts;
  const interruptions =
    report.interruptions.length > 0
      ? report.interruptions.slice(0, 5).map((value) => countedLine(value))
      : [countedLine({ label: "no interruptions indexed", count: 0 })];
  const denials =
    report.denials.length > 0
      ? report.denials.slice(0, 5).map((value) => countedLine(value))
      : [countedLine({ label: "no tool refusals indexed", count: 0 })];

  const tools =
    report.structural.toolUses.length > 0
      ? report.structural.toolUses
          .slice(0, 5)
          .map((value) => countedLine(value))
      : [countedLine({ label: "no tool calls indexed", count: 0 })];

  const activeDayLabel = countLabel({
    count: report.corpus.activeDays,
    singular: "active day",
    plural: "active days",
  });
  const originLabel = countLabel({
    count: report.originCount,
    singular: "origin",
    plural: "origins",
  });
  const batchLabel = countLabel({
    count: options.deepLearningPreview.extractionBatches,
    singular: "reconciliation batch",
    plural: "reconciliation batches",
  });
  const sessionLabel = countLabel({
    count: report.corpus.sessions,
    singular: "session",
    plural: "sessions",
  });
  const refusalCount = corrections.permissionDenials;
  const refusalCountLabel =
    refusalCount === 1 ? "once" : `${refusalCount} times`;
  const networkNotice = options.networkCallsMade
    ? ""
    : " No network calls were made.";
  const corpusLine = [
    `  Read ${report.corpus.sessions} ${sessionLabel}, ${megabytes} MB,`,
    `${report.corpus.activeDays} ${activeDayLabel} across`,
    `${report.originCount} ${originLabel}.${networkNotice}`,
  ].join(" ");

  return [
    corpusLine,
    "",
    "  Interaction markers found",
    countedLine({ label: "interruptions", count: corrections.interruptions }),
    countedLine({
      label: "permission denials",
      count: corrections.permissionDenials,
    }),
    countedLine({
      label: "answered questions",
      count: corrections.answeredQuestions,
    }),
    countedLine({ label: "resolved plans", count: corrections.resolvedPlans }),
    "",
    "  Observed interruption contexts",
    ...interruptions,
    "",
    `  Observed permission denials ${refusalCountLabel}`,
    ...denials,
    "",
    "  When the agent asked, you answered",
    ratioLine({
      label: "agent questions",
      count: corrections.answeredQuestions,
      total: report.askedQuestions,
    }),
    ratioLine({
      label: "presented plans",
      count: corrections.resolvedPlans,
      total: report.presentedPlans,
    }),
    "",
    "  Your most used agent tools",
    ...tools,
    "",
    "  Deep learning would send",
    countedLine({
      label: "eligible user steering episodes",
      count: options.deepLearningPreview.eligibleSteeringEpisodes,
    }),
    countedLine({
      label: batchLabel,
      count: options.deepLearningPreview.extractionBatches,
    }),
    "",
    resultLine({
      eligibleSteeringEpisodes:
        options.deepLearningPreview.eligibleSteeringEpisodes,
      deepChangesProposed: options.deepChangesProposed,
      profileUpdated: options.profileUpdated ?? false,
      pendingReview: options.pendingReview ?? 0,
    }),
  ].join("\n");
}
