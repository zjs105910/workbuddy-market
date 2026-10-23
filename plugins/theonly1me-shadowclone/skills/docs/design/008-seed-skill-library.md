# Bundled preferences and skills

## Problem

A short preference and a task workflow have different purposes. If every preference becomes a skill, the files are thin and repetitive. If a profile holds complete workflows, the startup guidance is too large.

## Decision

Ship two package-owned libraries that work without model calls:

- Eight preferences across four mutually exclusive axes. Each preference is a concise choice.
- Ten task skills: two alternative testing workflows and eight independent workflows.

Each preference has a stable identifier and belongs to an axis, so a declared choice can replace its sibling. Skills hold enough instruction to do a task, and they stay readable as ordinary files. The library does not force the comment policy of this repository on every user.

Validate metadata and reject unknown frontmatter fields. Each skill must have exactly one non-empty `Use when`, `Process`, `Guardrails`, and `Completion` section. Keep identifiers independent of display names, so edits to the prose do not change the installed identity.

## Consequences

Bundled guidance is a starting point. Users can select, edit, or replace it. Packaging owns the seed files. Installed user copies need ownership and conflict checks before updates.

## Verification

Parse every packaged preference and skill through the production loader. Check duplicate identities, conflicting axes, malformed metadata, missing or repeated sections, and package inclusion. [Agent builds](024-agent-builds.md) adds a visual way to select this library alongside user-created skills.
