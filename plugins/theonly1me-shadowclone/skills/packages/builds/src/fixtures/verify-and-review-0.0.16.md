---
name: verify-and-review
description: Verify changed behavior and inspect the final diff before presenting completed work. Use when an implementation, fix, refactor, or documentation change is ready for handoff.
metadata:
  shadowclone-category: review
  shadowclone-section: workflow
  shadowclone-applies-when: preparing completed work for review or handoff
---
# Verify and Review Before Finishing

## Use when

Code or documentation changes are ready for handoff. Answers to questions do not need this workflow; answer them directly.

## Process

1. Identify changed behavior, data paths, interfaces, and public claims. Read the repository's required checks.
2. Run focused verification, then the required gate. Repeat broad checks only when later changes or failures justify it.
3. Review the full diff with surrounding context, including untracked files. Check for generated output, diagnostics, secrets, and unrelated edits.
4. For changed data paths, trace logs, errors, writes, and network requests to their source and required redaction boundary.
5. Compare affected docs and diagrams with the implementation. Exercise changed interfaces and inspect their rendered state.
6. Report checks and results, separating pre-existing failures and unverified behavior from regressions.

## Guardrails

Match claims to checks or direct observations. A successful build does not prove an unexercised runtime path works. Keep captured user content out of reports unless it has crossed the required redaction boundary.

Preserve unrelated work. An existing dirty worktree is not a reason to delete another contributor's changes or claim that the whole tree is clean.

## Completion

The final diff has been reviewed, required checks have run, and the handoff states the evidence and material limitations.
