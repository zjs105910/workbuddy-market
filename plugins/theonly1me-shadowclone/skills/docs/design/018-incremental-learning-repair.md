# Repairing incremental learning

## Problem

Parsing could drop older profiles. Targeted learning could select old sessions instead of the requested one. A moving time window could permanently skip unprocessed history.

## Decision

Migrate recognized legacy records and preserve manual text and lifecycle decisions. Reject malformed or ambiguous files before any destructive write. An empty parse does not permit the replacement of an existing profile.

When the caller requests a session, select the newest eligible evidence from that session. Background catch-up walks through the unprocessed history with a durable ledger. It does not sample a recent window repeatedly. Source hashes tell new material from content that the system already processed.

Checkpoint bounded batches and resume from completed work. Publication failure must remain visible and recoverable. [Skills delivery](023-skills-as-delivery.md) later made pending publication independent of capture completion. So a finished capture batch cannot hide unpublished guidance.

## Verification

Cover legacy and malformed profiles, repeated catch-up, and budget exhaustion. Cover the requested session among many older sessions, deleted or truncated sources, and interruption between learning and publication. Preserve user edits and rejected records throughout recovery.
