# Separating observations from learned guidance

## Problem

Command counts and other structural signals describe a session but do not establish a durable preference. Turning them directly into rules gives weak evidence more authority than it deserves.

## Decision

Keep structural observations in a local learning report. Normal ingestion and signal derivation need no model call. They do not create semantic rules through heuristics.

Deep learning interprets bounded, redacted evidence through the selected engine. Its output must pass reconciliation and activation rules before publication. Evaluation must use the same semantic path. It cannot substitute heuristics when a model call fails.

This distinction applies to the learning stages. Initial setup can explicitly authorize a bounded first model pass, as [launch readiness](019-launch-readiness.md) describes.

## Verification

Check that ordinary ingestion produces reports without model calls or new mined guidance. A failed semantic call must leave a failure or pending result, never a fabricated rule. Reports must stay useful without exposing captured text in logs.
