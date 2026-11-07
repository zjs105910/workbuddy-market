import type { ReconciliationChange } from "./types";

function sourceLabel(change: ReconciliationChange): string {
  return change.before?.source ?? "mined";
}

export function renderReconciliationChanges(options: {
  readonly changes: readonly ReconciliationChange[];
  readonly rejectedMatches?: number;
  readonly droppedRules?: readonly { readonly title: string; readonly reason: string }[];
}): string {
  const droppedRules = options.droppedRules ?? [];

  if (options.changes.length === 0 && !options.rejectedMatches && droppedRules.length === 0) {
    return "No profile changes proposed.";
  }

  const blocks = options.changes.map((change) => {
    const proposal = change.after.proposal?.text;

    return [
      `${change.kind.toUpperCase()}: ${change.after.title}`,
      `Source: ${sourceLabel(change)}`,
      `Current: ${change.before?.body ?? "No existing guidance"}`,
      `Observed: ${change.observed || "No comparison supplied"}`,
      ...(proposal ? [`Proposal: ${proposal}`] : []),
      `Status: ${change.after.status}`,
      `Evidence: ${change.after.evidence.for.length} supporting, ${change.after.evidence.against.length} contradicting`,
    ].join("\n");
  });

  if (options.rejectedMatches) {
    blocks.push(
      `${options.rejectedMatches} proposed rule matched rejected guidance and was omitted.`,
    );
  }

  if (droppedRules.length > 0) {
    blocks.push(
      [
        `${droppedRules.length} learned rule${droppedRules.length === 1 ? " was" : "s were"} dropped while merging:`,
        ...droppedRules.map((rule) => `- ${rule.title}: ${rule.reason}`),
      ].join("\n"),
    );
  }

  return blocks.join("\n\n");
}
