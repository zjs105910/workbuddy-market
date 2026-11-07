import { findingBody } from "./publish/format";
import { neutralizeText } from "./publish/neutralize";
import type { ReviewResult } from "./types";

function plural(options: { readonly count: number; readonly word: string }): string {
  return `${options.count} ${options.word}${options.count === 1 ? "" : "s"}`;
}

function toolchainTable(result: ReviewResult): string {
  if (result.toolchain.length === 0) {
    return "No toolchain checks ran.";
  }

  const rows = result.toolchain.map(
    (entry) => `| ${entry.stack} | ${entry.tool} | ${entry.status} | ${entry.newDiagnostics} | ${entry.detail.replaceAll("|", "\\|").replaceAll("\n", " ")} |`,
  );

  return ["| Stack | Tool | Status | New diagnostics | Detail |", "| --- | --- | --- | ---: | --- |", ...rows].join("\n");
}

export function reviewMarkdown(result: ReviewResult): string {
  const { pull, statistics } = result;
  const target = pull.number === null ? null : { repository: pull.repository, headSha: pull.headSha };
  const header = [
    pull.number === null ? `# Review of ${pull.repository} at ${pull.headSha.slice(0, 7)}` : `# Review of ${pull.repository}#${pull.number}`,
    "",
    `Head \`${pull.headSha.slice(0, 7)}\` against \`${pull.baseRefName}\` (\`${pull.baseSha.slice(0, 7)}\`). Model ${result.model}. ${plural({ count: result.findings.length, word: "finding" })}.`,
    "",
    `The model returned ${plural({ count: statistics.modelFindings, word: "finding" })}, and ${statistics.droppedForEvidence} failed the evidence check. Built-in rules matched ${statistics.certainRuleHits} certain and ${statistics.signalRuleHits} signal lines. The review took ${Math.round(statistics.durationMilliseconds / 1000)} seconds.`,
  ];
  const findings =
    result.findings.length === 0
      ? ["No defect survived its refuter and the evidence check."]
      : result.findings.map(
          (finding, index) => `## ${index + 1}. \`${finding.path}:${finding.line}\`\n\n${findingBody({ finding, target, refutation: true })}`,
        );
  const dropped =
    result.dropped.length > 0
      ? ["## Left out", "", ...result.dropped.map((entry) => `- ${neutralizeText(entry.title)} (\`${entry.path}:${entry.line}\`): ${neutralizeText(entry.reason)}`), ""]
      : [];
  const correction = {
    none: [],
    ran: ["The first answer had problems, so one correction round ran:", ...result.rejections.map((rejection) => `- ${neutralizeText(rejection)}`)],
    failed: ["The first answer had problems, and the correction round failed."],
  }[statistics.correctionRound];
  const droppedCandidates =
    result.candidates.dropped.length > 0
      ? [
          "## Signals checked and dropped",
          "",
          ...result.candidates.dropped.map((entry) => `- ${entry.id} ${neutralizeText(entry.title)} (\`${entry.path}:${entry.line}\`): ${neutralizeText(entry.reason)}`),
          "",
        ]
      : [];
  const undecided =
    result.candidates.undecided.length > 0
      ? ["## Signals with no decision", "", ...result.candidates.undecided.map((entry) => `- ${entry.id} ${neutralizeText(entry.title)} (\`${entry.path}:${entry.line}\`)`), ""]
      : [];
  const skipped = result.skippedPaths.length > 0 ? ["## Not reviewed", "", ...result.skippedPaths.map((skippedPath) => `- \`${skippedPath}\` (generated)`)] : [];

  const sections = [...header, ...(correction.length > 0 ? ["", ...correction] : []), "", ...findings.flatMap((section) => [section, ""]), ...dropped, ...droppedCandidates, ...undecided];

  return `${[...sections, "## Toolchain", "", toolchainTable(result), "", ...skipped].join("\n").trimEnd()}\n`;
}
