import type { LineRange, ReviewResult } from "../types";
import { findingBody } from "./format";
import { neutralizeText } from "./neutralize";

export type ReviewComment = {
  readonly path: string;
  readonly line: number;
  readonly side: "RIGHT";
  readonly body: string;
};

export type ReviewPayload = {
  readonly commit_id: string;
  readonly event: "COMMENT";
  readonly body: string;
  readonly comments: readonly ReviewComment[];
};

export const reviewMarker = "<!-- shadowclone-review -->";

function isCommentable(options: {
  readonly ranges: readonly LineRange[] | undefined;
  readonly line: number;
}): boolean {
  return (options.ranges ?? []).some(([start, end]) => options.line >= start && options.line <= end);
}


function summary(options: {
  readonly result: ReviewResult;
  readonly inlineCount: number;
}): string {
  const { result, inlineCount } = options;
  const head = result.pull.headSha.slice(0, 7);
  const count = result.findings.length;
  const lines = [
    count === 0
      ? `Shadowclone reviewed ${head} and found no defect that it could confirm.`
      : `Shadowclone reviewed ${head} and confirmed ${count} ${count === 1 ? "finding" : "findings"}, ${inlineCount} inline.`,
  ];

  if (result.candidates.dropped.length > 0) {
    lines.push(`${result.candidates.dropped.length} rule hits and toolchain diagnostics were checked and dropped with a reason.`);
  }

  if (result.candidates.undecided.length > 0) {
    lines.push(`${result.candidates.undecided.length} rule hits or toolchain diagnostics got no decision: ${result.candidates.undecided.map((entry) => entry.id).join(", ")}.`);
  }

  if (result.statistics.droppedForEvidence > 0) {
    lines.push(`${result.statistics.droppedForEvidence} candidate findings were left out because their evidence did not match the code.`);
  }

  if (result.skippedPaths.length > 0) {
    lines.push(`Not reviewed: ${result.skippedPaths.map((skippedPath) => `\`${skippedPath}\``).join(", ")}.`);
  }

  const unfinished = result.toolchain.filter((entry) => entry.status !== "ran");

  if (unfinished.length > 0) {
    lines.push(`Toolchain checks that did not finish: ${unfinished.map((entry) => `${entry.tool} (${entry.status})`).join(", ")}.`);
  }

  return lines.join("\n\n");
}

export function reviewPayload(result: ReviewResult): ReviewPayload {
  const inline = result.findings.filter((finding) =>
    isCommentable({ ranges: result.commentableLines[finding.path], line: finding.line }),
  );
  const outside = result.findings.filter((finding) => !inline.includes(finding));
  const target = { repository: result.pull.repository, headSha: result.pull.headSha };
  const outsideText = outside.map(
    (finding) => `\`${neutralizeText(finding.path)}:${finding.line}\`\n\n${findingBody({ finding, target, refutation: false })}`,
  );

  return {
    commit_id: result.pull.headSha,
    event: "COMMENT",
    body: [summary({ result, inlineCount: inline.length }), ...outsideText, reviewMarker].join("\n\n"),
    comments: inline.map((finding) => ({
      path: finding.path,
      line: finding.line,
      side: "RIGHT",
      body: findingBody({ finding, target, refutation: false }),
    })),
  };
}
