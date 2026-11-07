---
name: verify-review-findings
description: 'Use when a pull request has review comments or bot findings to check. Also use it when the user says "are these comments right?", "triage the review", or "check what the bot found". Checks each finding against the code at the head of the pull request, and confirms the file, the line, and the claim. Asks what each suggested fix would break, reports a verdict for each finding, and waits. Not for writing the fix (use `scope-confirmed-changes`).'
metadata:
  shadowclone-category: review
  shadowclone-section: workflow
  shadowclone-applies-when: when a pull request has review comments or bot findings
  shadowclone-voice: "true"
---
# Verify Review Findings

## Use when

A pull request has review comments, bot findings, or a list of issues from another agent. A finding is a claim, not a fact. Check each one before you change code or reply.

## Gates

1. Did you read each finding at the head commit of the pull request? A finding about an older commit can be stale.
2. For each finding, do the file and the line exist, and does the code there do what the finding says?
3. Can you show the claim with a test, a command, or the code itself? If not, label it as not verified.
4. Did you ask what each suggested fix would break, such as a caller, a test, or a documented behavior?
5. Does each finding have a verdict: confirmed, partly right, wrong, stale, or not verified?
6. Did you wait for the user before you changed code or replied to a reviewer?

## Process

Write in the user's voice. Before you write, read `~/.agents/voice.md`. If it does not exist, build it once from the user's merged pull requests, review comments, and commit messages. Use only text that the user wrote, and name those sources in your handoff. Never overwrite an existing or linked `voice.md`.

1. Fetch the pull request, and check out its head commit. Write down the commit hash.
2. List each finding in one table, with its source, its `file:line`, and its claim.
3. For each finding, read the code at that location and its callers. Compare the claim with the real behavior.
4. When the claim is about behavior, run a focused test or a command that shows it.
5. For each suggested fix, list what it changes for callers, tests, and users. A fix that is right in one place can break another place.
6. Give each finding a verdict, with the evidence that supports it.
7. Put the confirmed findings first, with the highest risk at the top.
8. Report the table, and wait. Change code or reply only after the user decides.

## Example

**Situation:** A review bot says that a function can return null and crash its caller. It suggests a null check.
**Easy route:** Add the null check, and reply "Fixed".
**Hidden cost:** The function never returns null, because a type guard on the line above handles that case. The extra check hides the real contract, and the reply tells the reviewer something false.
**Best route:** Read the function at the head commit, and run its test with an empty input. Report the finding as wrong, with the line that handles the case.
**Evidence:** The test with the empty input passed at the head commit. The report quoted the guard at its `file:line` and gave the verdict "wrong".

## Guardrails

- Never change code or post a reply before the user decides.
- Do not accept a finding because a bot or a senior reviewer wrote it. Do not reject it for that reason either.
- Quote the code that proves each verdict. Do not paraphrase it.
- Keep each finding separate. Do not merge two findings into one verdict.
- A finding that you cannot check stays "not verified" in the report.

## Completion

- The head commit hash that you checked.
- A table row for each finding: the source, the `file:line`, the claim, the verdict, and the evidence.
- Each command or test that you ran, with its result line.
- For each confirmed finding, what its fix changes for callers and tests.
