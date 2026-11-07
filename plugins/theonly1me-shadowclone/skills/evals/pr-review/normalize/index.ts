import { z } from "zod";
import { reviewResultSchema } from "@shadowclone/review";
import { activitySchema } from "./github";
import { type NormalizedFinding, plainText } from "./text";

export type { NormalizedFinding } from "./text";

const bodyFindingStart = /\n\n(?=`[^`\n]+:\d+`\n)/;

export function shadowcloneFindings(options: { readonly caseId: string; readonly raw: unknown; readonly startedAt: string }): readonly NormalizedFinding[] {
  const activity = activitySchema.parse(options.raw);
  const review = activity.reviews.find((entry) => (entry.body ?? "").includes("<!-- shadowclone-review -->") && (entry.submitted_at ?? "") >= options.startedAt);

  if (review === undefined) {
    return [];
  }

  const inline = activity.reviewComments
    .filter((comment) => comment.pull_request_review_id === review.id)
    .map((comment) => ({ arm: "shadowclone", caseId: options.caseId, path: comment.path, line: comment.line ?? comment.original_line ?? null, text: plainText(comment.body) }));
  const outside = (review.body ?? "")
    .split(bodyFindingStart)
    .slice(1)
    .flatMap((section) => {
      const match = /^`([^`\n]+):(\d+)`\n/.exec(section);

      return match?.[1] && match[2] ? [{ arm: "shadowclone", caseId: options.caseId, path: match[1], line: Number(match[2]), text: plainText(section.slice(match[0].length)) }] : [];
    });

  return [...inline, ...outside];
}

export function greptileFindings(options: { readonly caseId: string; readonly raw: unknown; readonly startedAt: string }): readonly NormalizedFinding[] {
  const activity = activitySchema.parse(options.raw);
  const reviews = new Set(activity.reviews.filter((entry) => /greptile/i.test(entry.user.login) && (entry.submitted_at ?? "") >= options.startedAt).map((entry) => entry.id));

  return activity.reviewComments
    .filter((comment) => comment.pull_request_review_id !== null && reviews.has(comment.pull_request_review_id))
    .map((comment) => ({ arm: "greptile", caseId: options.caseId, path: comment.path, line: comment.line ?? comment.original_line ?? null, text: plainText(comment.body) }));
}

const openqodexFindingSchema = z.object({
  file_path: z.string(),
  line_number: z.number(),
  title: z.string(),
  description: z.string(),
  problem: z.string().optional(),
  consequence: z.string().optional(),
  fix: z.string().optional(),
  suggested_change: z.string().nullable(),
});

const openqodexReportSchema = z.object({ findings: z.array(openqodexFindingSchema), outside_change: z.array(openqodexFindingSchema) });

export function openqodexFindings(options: { readonly arm: string; readonly caseId: string; readonly raw: unknown }): readonly NormalizedFinding[] {
  const report = openqodexReportSchema.parse(options.raw);

  return [...report.findings, ...report.outside_change].map((finding) => ({
    arm: options.arm,
    caseId: options.caseId,
    path: finding.file_path,
    line: finding.line_number,
    text: plainText([finding.title, finding.problem ?? finding.description, finding.consequence ?? "", finding.fix ?? finding.suggested_change ?? ""].join(" ")),
  }));
}

export function localShadowcloneFindings(options: { readonly arm: string; readonly caseId: string; readonly raw: unknown }): readonly NormalizedFinding[] {
  return reviewResultSchema.parse(options.raw).findings.map((finding) => ({
    arm: options.arm,
    caseId: options.caseId,
    path: finding.path,
    line: finding.line,
    text: plainText([finding.title, finding.explanation, finding.failureScenario, finding.suggestion ?? ""].join(" ")),
  }));
}
