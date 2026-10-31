import type { HarnessCheckReport, HarnessFinding } from "./types";

export type CheckFormat = "human" | "json" | "claude-stop";

const maximumStopFindings = 30;

function location(finding: HarnessFinding): string {
  return finding.line === null
    ? finding.path
    : `${finding.path}:${finding.line}`;
}

export function renderCheckReport(options: {
  readonly report: HarnessCheckReport;
  readonly format: CheckFormat;
}): {
  readonly stdout: string;
  readonly stderr: string;
  readonly exitCode: number;
} {
  const errors = options.report.findings.filter(
    (finding) => finding.severity === "error",
  );

  if (options.format === "json") {
    return {
      stdout: `${JSON.stringify(options.report, null, 2)}\n`,
      stderr: "",
      exitCode: errors.length > 0 ? 1 : 0,
    };
  }

  if (options.format === "claude-stop") {
    if (errors.length === 0) {
      return { stdout: "", stderr: "", exitCode: 0 };
    }

    const listed = errors
      .slice(0, maximumStopFindings)
      .map(
        (finding) => `- ${location(finding)} ${finding.rule}: ${finding.fix}`,
      );
    const more =
      errors.length > maximumStopFindings
        ? [
            `- and ${errors.length - maximumStopFindings} more; run \`shadowclone check --changed\` to see them.`,
          ]
        : [];

    return {
      stdout: "",
      stderr: [
        `Shadowclone check found ${errors.length} problem(s) in this repository's changed files. Fix them before you finish:`,
        ...listed,
        ...more,
      ].join("\n"),
      exitCode: 2,
    };
  }

  const warnings = options.report.findings.length - errors.length;
  const lines = [
    `shadowclone check: ${errors.length} error(s), ${warnings} warning(s) in ${options.report.checkedFiles} file(s)`,
    ...options.report.findings.map(
      (finding) =>
        `${finding.severity} ${location(finding)} ${finding.rule}: ${finding.fix}`,
    ),
  ];

  return {
    stdout: `${lines.join("\n")}\n`,
    stderr: "",
    exitCode: errors.length > 0 ? 1 : 0,
  };
}
