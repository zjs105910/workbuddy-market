# Automatic preference learning

## Problem

Manual learning commands left guidance stale between sessions. Automatic learning needed to tell a durable instruction from a one-off task request. It also needed to keep a clear consent boundary.

## Decision

Treat explicit durable user steering as eligible evidence after one session. Inferred patterns need support from three independent sessions. Read interruptions and corrections in conversation context, including the next user message. An interruption alone is not evidence of dissatisfaction.

Separate capture consent, model-learning consent, and automatic publication authority. Session hooks can schedule bounded background work only after the relevant opt-ins. [Useful-session attribution](017-self-improving-agent-environment.md) later narrowed this to sessions that the main agent marks as containing reusable guidance.

Use session identities and content hashes to avoid processing unchanged evidence again. Share invocation, time, and supported cost limits across the run. Checkpoint completed work. If publication cannot finish, show the pending changes.

Keep user edits and explicit choices authoritative. Record revisions, so Shadowclone can explain and undo learned changes. `remember` records direct user guidance with an explicit scope. It does not justify unrelated global promotion.

When you store explicit preferences, escape both `-->` and `--!>`, and also escape comment openings. Then comment delimiters stay literal guidance. Cover both forms through preference publication.

## Verification

Test durable instructions, temporary requests, independent-session thresholds, repeated hooks, cancellation, and revoked consent. Check that history and undo preserve unrelated edits. Check that failed background work cannot replace active guidance with incomplete output.
