import { existsSync, mkdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { runProcess } from "@shadowclone/core";
import type { ArmName, ArmRun, ArmRunner } from "./types";

export const openqodexVersion = "0.10.0";

export async function openqodexReview(options: {
  readonly arm: ArmName;
  readonly caseId: string;
  readonly number: number;
  readonly cwd: string;
  readonly target: readonly string[];
  readonly model: string;
  readonly directory: string;
}): Promise<ArmRun> {
  const startedAt = new Date().toISOString();
  const reportDirectory = path.join(options.directory, "report");

  mkdirSync(reportDirectory, { recursive: true });

  const result = await runProcess({
    arguments: [
      "npx",
      "-y",
      `openqodex@${openqodexVersion}`,
      "review",
      ...options.target,
      "--reviewer",
      "claude",
      "--reviewer-web",
      "on",
      "--timeout",
      "1800",
      "--report-dir",
      reportDirectory,
      "--format",
      "json",
    ],
    cwd: options.cwd,
    environment: { ...process.env, ANTHROPIC_MODEL: options.model },
    timeoutMilliseconds: 40 * 60_000,
  }).catch((error: unknown) => ({ exitCode: -1, stdout: "", stderr: error instanceof Error ? error.message : String(error) }));
  const reportFile = path.join(reportDirectory, "report.json");
  const report: unknown = existsSync(reportFile) ? JSON.parse(readFileSync(reportFile, "utf8")) : null;

  return {
    arm: options.arm,
    caseId: options.caseId,
    number: options.number,
    startedAt,
    finishedAt: new Date().toISOString(),
    status: report === null ? "failed" : "done",
    detail: `exit ${result.exitCode}: ${result.stderr.trim().split("\n").slice(-3).join(" | ").slice(0, 400)}`,
    raw: report,
  };
}

export const runOpenqodex =
  (options: { readonly checkout: string; readonly model: string }): ArmRunner =>
  ({ entry, directory }) =>
    openqodexReview({ arm: "openqodex", caseId: entry.id, number: entry.number, cwd: options.checkout, target: [`#${entry.number}`], model: options.model, directory });
