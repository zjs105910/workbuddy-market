import type { FixedReport } from "./report";
import { fixedArms } from "./definition";

export function fixedReportText(report: FixedReport): string {
  const tasks = [...new Set(report.cells.map((cell) => cell.taskId))];
  const rows = tasks.map((taskId) => [taskId, ...fixedArms.map((arm) => {
    const cells = report.cells.filter((cell) => cell.taskId === taskId && cell.arm === arm);
    const passed = cells.filter((cell) => cell.verdict === "pass").length;
    const unknown = cells.filter((cell) => cell.verdict === "unknown").length;
    return `${passed}/${cells.length} passed${unknown > 0 ? `, ${unknown} unknown` : ""}`;
  })].join(" | "));
  const scores = report.arms.map((arm) => `${arm.arm}: ${arm.score === null ? "incomplete" : `${arm.score.toFixed(1)}/100`}; preference adherence: ${arm.adherenceScore === null ? "incomplete" : `${arm.adherenceScore.toFixed(1)}/100`}`);
  return ["task | bare | profile | shadowclone", ...rows, "", ...scores, `Suite ${report.status}. See report.json for individual checks, evidence, and confidence intervals.`].join("\n");
}
