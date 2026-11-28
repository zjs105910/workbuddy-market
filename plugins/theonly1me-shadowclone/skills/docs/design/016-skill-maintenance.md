# Maintaining existing skills

This introduced profile-backed skill amendments. [Skills delivery](023-skills-as-delivery.md) later allowed complete workflow updates and creation without an aggregated profile.

## Problem

Newly learned preferences did not improve the skills that an agent already used. Copying every profile rule into every skill would create duplication and erase the purpose of each workflow.

## Decision

Review the entire consented library of the selected agent, including installed third-party skills. Match supported guidance to relevant workflows and propose exact passage changes. Keep unrelated instructions, supporting resources, permissions, and invocation settings unchanged.

Separate permission to read a library from permission to edit it. User-authored skills need explicit write authorization. Provider-owned packages stay unchanged. Personal amendments belong in local companions. Conflicting manual edits need review.

Inspect resource structure, but do not treat arbitrary resource contents as learning input. Use bounded model execution that the learning run shares. Review routing as well as body text, so an updated skill stays discoverable for the intended task.

Publish revisions with fingerprints and backups. An intervening edit blocks replacement. Report skipped and pending work, so nobody mistakes a successful review for complete publication.

A Markdown link to a local file must resolve inside the skill's folder. A path that a skill only names in backticks, such as `references/voice.md`, can belong to another skill. A user-authored skill stays valid when that file is missing. The host loads the skill the same way, and the wizard then offers it. Text that a model proposes still needs every named supporting file. So a learned edit cannot point at a file that does not exist.

## Verification

Test whole-library review, relevant and irrelevant matches, resource preservation, package companions, consent, conflicts, interrupted publication, and undo. See [the maintenance guide](../guides/skills.md) for current commands and permissions.
