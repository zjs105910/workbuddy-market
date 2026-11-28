import { z } from "zod";

export const labels = ["real", "minor", "wrong"] as const;

export const judgmentSchema = z.object({
  findings: z.array(z.object({ id: z.string(), label: z.enum(labels), reason: z.string().max(600) })),
  detected: z.array(z.string()),
});

export type Judgment = z.infer<typeof judgmentSchema>;

export type BlindFinding = { readonly id: string; readonly path: string; readonly line: number | null; readonly text: string };

export function judgePrompt(options: {
  readonly title: string;
  readonly diff: string;
  readonly findings: readonly BlindFinding[];
  readonly defect: { readonly description: string; readonly fixDiff: string } | null;
}): string {
  const defect =
    options.defect === null
      ? "This pull request has no known defect. Leave detected empty."
      : `A later pull request repaired a defect that this pull request introduced.
<known_defect>
${options.defect.description}
</known_defect>
<later_fix>
${options.defect.fixDiff}
</later_fix>
List in detected the id of each finding that identifies this same defect, even in other words. A finding that only touches the same file does not count.`;

  return `You judge findings from automated reviews of one pull request. The working directory is the pull request head. Read the code before you decide.

Label each finding:
- real: the change introduces the problem, and it causes a concrete failure, a security risk, or breaks a rule that the repository writes down.
- minor: the claim is true, but the impact is small, such as style, naming, or a rare case with little effect.
- wrong: the claim is false, the problem existed before the change, other code already handles it, or the finding cites code that is not there.

Judge each finding on its own. The findings come from several reviewers in random order.
${defect}

<pull_request_title>${options.title}</pull_request_title>
<findings>
${JSON.stringify(options.findings, null, 1)}
</findings>
<diff>
${options.diff}
</diff>`;
}
