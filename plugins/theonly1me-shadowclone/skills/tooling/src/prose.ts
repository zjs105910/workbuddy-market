import { listProseFiles } from "./prose/files";
import { linkFindings, type LinkFinding } from "./prose/links";
import { steFindings, type SteFinding } from "./prose/ste";

export type ProseReport = {
  readonly fileCount: number;
  readonly steErrors: readonly SteFinding[];
  readonly warningCount: number;
  readonly linkProblems: readonly LinkFinding[];
};

export async function checkProse(options: {
  readonly rootDirectory: string;
}): Promise<ProseReport> {
  const files = await listProseFiles(options);
  const findings = steFindings({ rootDirectory: options.rootDirectory, files });

  return {
    fileCount: files.length,
    steErrors: findings.filter((finding) => finding.level === "error"),
    warningCount: findings.filter((finding) => finding.level === "warning").length,
    linkProblems: await linkFindings({ rootDirectory: options.rootDirectory, files }),
  };
}

if (import.meta.main) {
  const report = await checkProse({ rootDirectory: process.cwd() });

  for (const finding of report.steErrors) {
    console.error(`${finding.file}:${finding.line}: ${finding.rule} ${finding.message}`);
  }

  for (const problem of report.linkProblems) {
    console.error(`${problem.file}:${problem.line}: link ${problem.message}`);
  }

  console.log(
    `prose: checked ${report.fileCount} files, found ${report.steErrors.length} plain English errors and ${report.linkProblems.length} link problems (${report.warningCount} warnings)`,
  );

  if (report.steErrors.length > 0 || report.linkProblems.length > 0) {
    process.exitCode = 1;
  }
}
