---
name: scope-confirmed-changes
description: 'Use when fixing a bug, a regression, or a confirmed review finding. Also use it when the user says "fix this bug", "it is broken", or "keep the change small". Reproduces the issue before any fix, with a test, a real command, or the real interface. After the fix, the same reproduction must pass. Keeps the change to confirmed, reachable behavior. Not for checking review comments before a fix (use `verify-review-findings`).'
metadata:
  shadowclone-category: change-control
  shadowclone-section: workflow
  shadowclone-applies-when: when fixing a bug, a regression, or a confirmed review finding
  shadowclone-voice: "true"
---
# Scope Confirmed Changes

## Use when

You fix a bug, a regression, or a review finding that you confirmed. Only a reproduction proves that a bug is real. Only the same reproduction after the fix proves that the fix works.

## Gates

1. Did you reproduce the issue before you changed code, with a test, a real command, or the real interface?
2. After the fix, does the same reproduction show the expected result?
3. If you could not reproduce the issue, did you label the cause as inferred, with the data and code that support it?
4. Does each changed line serve the fix, or a test or check that the fix needs?
5. Do all checks that passed before your change still pass?
6. If an approach caused a new regression, did you remove it instead of adding a second fix on top?

## Process

Write in the user's voice. Before you write, read `~/.agents/voice.md`. If it does not exist, build it once from the user's merged pull requests, review comments, and commit messages. Use only text that the user wrote, and name those sources in your handoff. Never overwrite an existing or linked `voice.md`.

1. Write the issue as a concrete input, the wrong result, and the expected result.
2. Reproduce it in the cheapest way that shows the real symptom:
   - a failing unit or integration test,
   - the real command in a temporary home, or
   - the real interface, such as browser or desktop automation when the host has it.
3. Keep the reproduction and its wrong output, because you run it again after the fix.
4. Find the cause in the code that the reproduction runs. Fix it at the boundary that owns it.
5. Run the same reproduction. It must now show the expected result.
6. Run the focused tests and the required check of the repository.
7. Read the diff. Remove each line that does not serve the fix or its proof.
8. If reproduction is impossible, say why. Reason from logs, data, and code, and label the conclusion as inferred.

## Example

**Situation:** A user reports that `sync` lost an edit to an installed skill. All unit tests pass.
**Easy route:** Read the code, guess that the copy check is wrong, and change it.
**Hidden cost:** A guess can be wrong, and nothing proves the fix. The edit can still disappear in the case that the user hit.
**Best route:** Reproduce the report. Install the skill, edit one copy, apply the build again, and run `sync`. The edit disappears. Fix the cause, and run the same steps again.
**Evidence:** Before the fix, the reproduction printed "Updated design-deep-modules to the bundled version (3 copies)." and the edit was gone. After the fix, it printed "Kept your edited copy of design-deep-modules at ..." and the edit stayed.

## Guardrails

- Keep the unrelated edits of the user in the worktree.
- Do not widen a public contract to fit an internal shortcut.
- Refactor only when the fix or its proof needs it.
- Do not add a guard for a case that cannot happen. Fix the cause of a case that can.
- Put each later review round in its own commit. Never rewrite pushed history.

## Completion

- The reproduction command or test, with the wrong output before the fix.
- The same reproduction after the fix, with the expected output.
- The focused test command and the required check, with their result lines.
- Each changed file, with the reason that it is in scope.
- For an issue that you could not reproduce: the reason, and the evidence for the inferred cause.
