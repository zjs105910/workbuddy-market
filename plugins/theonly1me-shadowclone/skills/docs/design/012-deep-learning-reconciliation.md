# Reconciling learned preferences

This introduced reconciliation for profiles. The same evidence and user-authority constraints inform current [skill maintenance](023-skills-as-delivery.md).

## Problem

Regenerating guidance from each batch could duplicate existing rules, reverse explicit choices, and lose rejections. A model-generated confidence score did not establish enough evidence to publish a change.

## Decision

Give the learner the existing guidance, relevant evidence, and prior user decisions. Return typed proposals to retain, add, revise, contradict, or retire guidance. Evidence tokens must refer to excerpts that the request supplied. The model cannot invent source identities.

Use named preference axes to propose a concrete sibling when a choice changes. Keep free-form guidance where no axis applies. Preserve declared, imported, and manually edited instructions while contradictory evidence awaits review.

Separate activation from confidence. The original design required three independent sessions for mined guidance. [Automatic preference learning](015-automatic-preference-learning.md) later allowed explicit durable user instructions from one session. It kept the stronger requirement for inferred behavior.

Tie checkpoints to the redacted prompt, the output schema, and the learner version. Read metadata and model-facing text from one bounded snapshot. Then reconciliation cannot pair a stale hash with different contents. Unless the caller explicitly authorizes application, preview the proposed changes.

## Verification

Test repeated evidence, invalid evidence tokens, axis conflicts, user edits, rejected proposals, and stale checkpoints. Test that model failures preserve published guidance. Mutation checks must prove the source-to-redaction wiring. This includes instruction titles and conditions that could also contain secrets.
