import type { ProfileProposal } from "@shadowclone/profile";
import type { PromptRule, ReconciliationExistingRule } from "./types";

export function reconciliationProposal(options: {
  readonly result: ReconciliationExistingRule;
  readonly promptRule: PromptRule;
}): ProfileProposal | null {
  const axis = options.promptRule.axisOptions.find(
    (entry) => entry.token === options.result.axisChoiceToken,
  );
  const title = axis?.title ?? options.result.proposedTitle;
  const body = axis?.body ?? options.result.proposedBody;

  if (!title || !body) {
    return options.promptRule.snapshot.rule.proposal;
  }

  return {
    kind: options.result.verdict === "narrows" ? "narrow" : "revise",
    text: axis
      ? `${title}\n\n${body}\n\nApplies when: ${axis.appliesWhen.join(", ")}`
      : `${title}\n\n${body}`,
  };
}
