---
name: prove-regression-tests
description: Prove that a regression test detects the defect it claims to guard by temporarily removing or inverting the enforcing change. Use when adding a test for a confirmed bug or review finding.
metadata:
  shadowclone-category: testing
  shadowclone-section: workflow
  shadowclone-applies-when: adding a regression test for a confirmed defect
---
# Prove Regression Tests

## Use when

A confirmed defect has a focused test and a fix. Verify that the test can detect the original failure.

## Process

1. Identify the smallest production change that enforces the fix.
2. Temporarily invert it to restore the defect while keeping the code compilable.
3. Print the changed lines with file and line numbers. Run the narrow test and confirm its assertion fails on the original symptom.
4. If it passes or fails for another reason, improve the test before claiming coverage.
5. Restore and display the enforcing lines, then rerun the same test and affected suite.

## Guardrails

Keep the mutation local and reversible. Preserve unrelated work and avoid destructive Git operations. Mutate production behavior, not the assertion.

A setup error, compilation failure, timeout, or unrelated assertion does not prove the regression. Restore the code before starting other work. Broaden the proof only when the fix covers distinct public behaviors.

## Completion

The visible inverse fails the intended assertion, restoration passes, and the final diff contains no proof mutation.

Report the test name, the inverse you applied, the assertion line that failed under it, and the passing run after restoring. Keep the reply to these facts. When a pull request exists, put full command output in its verification section instead of the reply.
