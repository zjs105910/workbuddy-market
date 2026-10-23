# Onboarding choices

This was the original terminal onboarding design. [Launch readiness](019-launch-readiness.md) simplified initial setup. [Agent builds](024-agent-builds.md) made the browser wizard the default way to choose skills.

## Problem

Consent questions without context made setup hard to follow. Users also needed a way to declare preferences before enough session evidence existed to learn them.

## Decision

Show the available guidance and the relevant source choices in a guided setup. Find source availability with the pre-consent boolean check. Then read only the sources that the user enables. Absent providers must not cause unnecessary questions.

Before you apply changes, preview the selected guidance and installation targets. Cancellation must leave configuration, guidance, and integrations unchanged. Repeating setup must reuse stable identities and preserve user edits. It must not add duplicate rules.

Keep declared choices separate from inferred preferences. Selecting a workflow is a direct user decision. Background learning needs its own consent.

## Verification

Test cancellation at every prompt, an empty machine, existing installations, conflicting choices, and repeated application. Confirm that the preview does not write or read unconsented source contents. The terminal and browser interfaces must use the same underlying configuration and publication rules.
