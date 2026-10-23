import type { WorkflowReport } from "./report";

const labels = { bare: "Bare", skills: "Existing user skills", routing: "Existing skills + Shadowclone routing", deep: "Existing skills + routing + deep learning" };

export function workflowReportText(report: WorkflowReport) {
  return [`Fixed four-setup eval: ${report.status}`, `${report.configuration.model} (${report.configuration.effort}) on ${report.configuration.engine}`,
    "Score: share of applicable preferences followed, with equal weight per task.",
    ...report.arms.map(arm => `${labels[arm.arm]}: ${arm.preferenceScore === null ? "incomplete" : `${arm.preferenceScore.toFixed(1)}%`} (${arm.preferencesPassed}/${arm.expectedPreferences} checks, ${arm.preferencesUnknown} unknown)`),
    "Correctness, safety, and whole-task success are recorded separately in report.json.",
    `Learning preparation: ${report.learning.calls} calls, ${report.learning.processedEpisodes} episodes, ${report.learning.publishedRules} published rules.`,
    "Seven public development tasks; these results do not establish held-out performance."].join("\n");
}
