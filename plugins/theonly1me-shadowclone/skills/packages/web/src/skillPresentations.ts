export const skillPresentations: Readonly<
  Record<string, { readonly title: string; readonly summary: string }>
> = {
  "design-deep-modules": {
    title: "Deep modules",
    summary:
      "Keep interfaces small and useful. Put complexity behind a clear boundary so callers have less to understand.",
  },
  "typescript-type-safety": {
    title: "Explicit types",
    summary:
      "Represent valid states in the type system. Narrow uncertain values and keep unsafe assertions out of the implementation.",
  },
  "verify-review-findings": {
    title: "Check review findings",
    summary:
      "Check each review comment against the code at the pull request head, and report a verdict before any change or reply.",
  },
  "plan-with-review-page": {
    title: "Plan first",
    summary:
      "Read the code, ask one round of decisions with a recommendation, and share one plan with a review page before any edit.",
  },
  "write-plain-english": {
    title: "Plain English",
    summary:
      "Write short sentences with one idea each and no dashes, in the user's voice. A checker reports long sentences and dashes.",
  },
  "choose-by-consequence": {
    title: "Fail loudly",
    summary:
      "Compare each shortcut by what it does to the user's files and output. Pick the option that fails loudly and keeps counts true.",
  },
  "scope-confirmed-changes": {
    title: "Reproduce, then fix",
    summary:
      "Reproduce the bug before any fix, then run the same reproduction after it. Keep the change to confirmed behavior.",
  },
  "diagnose-before-editing": {
    title: "Find the cause",
    summary:
      "Reproduce the failure, make it smaller, and test one cause at a time until one cause predicts the symptom.",
  },
  "tests-that-catch-bugs": {
    title: "Tests that catch bugs",
    summary:
      "Write a few tests that each name the bug they catch, check what the user sees, and fail when the fix is removed.",
  },
  "verify-and-review": {
    title: "Verify the real outcome",
    summary:
      "Run what the user runs, read every count and exit code, and label each claim as measured, inferred, or not verified.",
  },
  "research-primary-sources": {
    title: "Go to the source",
    summary:
      "Check authoritative documentation and original evidence when a technical decision depends on facts that need verification.",
  },
  "planning-first": {
    title: "Plan the change",
    summary:
      "Establish the approach before implementation so the scope, decisions, and intended outcome are clear.",
  },
  "planning-when-costly": {
    title: "Plan when it matters",
    summary:
      "Move directly on straightforward tasks. Pause for a plan when the cost, uncertainty, or consequences call for one.",
  },
  "questions-autonomous": {
    title: "Keep moving",
    summary:
      "Use judgment to resolve routine choices. Ask when missing information changes the outcome or an action needs authorization.",
  },
  "questions-early": {
    title: "Ask early",
    summary:
      "Resolve meaningful uncertainty with the user before investing in an implementation built on the wrong assumption.",
  },
  "resolve-conflicts-by-intent": {
    title: "Preserve intent",
    summary:
      "Understand what both sides of a merge are trying to achieve. Resolve the conflict and verify the combined behavior.",
  },
  "dependencies-existing": {
    title: "Know your tools",
    summary:
      "Look for a solution in the existing stack before adding another dependency.",
  },
  "dependencies-mature": {
    title: "Choose proven tools",
    summary:
      "Use established, focused packages when they provide substantial reusable logic and justify the dependency.",
  },
  "refactor-boundaries": {
    title: "Improve boundaries",
    summary:
      "Make a refactor when it improves responsibilities and simplifies the change. Keep its purpose connected to the task.",
  },
  "refactor-preserve": {
    title: "Respect the structure",
    summary:
      "Work within the current structure and preserve unrelated code while making the requested change.",
  },
};
