# Importing repository guidance

The original importer produced profile rules. [Skills delivery](023-skills-as-delivery.md) keeps imported guidance as evidence. It does not republish instructions that the repository already supplies.

## Problem

Users had already written useful instructions in native agent files. Ignoring those files could produce duplicate or contradictory learned guidance.

## Decision

Add a separate `declared-rules` source, off by default. Read only supported root instruction files and directly supported skill locations. Do not search the repository recursively or follow symbolic links. Limit a read to 256 files and 2 MiB.

Resolve text through the learning redaction boundary. Keep the exact repository scope. Derive stable identities from the source path and heading, so repeated imports update the same records. Git metadata still needs separate consent. Importing instructions does not authorize remote discovery.

Imported instructions have user-owned authority. Preserve manual edits, source removals, and rejected records. Disagreement from mined evidence becomes a proposal. It cannot silently replace an explicit instruction.

## Tradeoffs and verification

A closed set of paths misses unconventional instruction locations, but it makes consent predictable. Adding a location widens the source and needs a documented decision.

Use fixtures for supported paths, symlinks, limits, redaction, repeated imports, moved or deleted sections, manual edits, and scope isolation. [Data handling](../data-handling.md) lists the current source locations.
