# Skills as the learning delivery format

## Problem

An aggregated profile compresses every preference into one startup budget. Copying fragments from that profile into existing skills loses detail and cannot create a missing workflow. Maintaining both representations also hides which instruction the agent used.

## Decision

Keep complete guidance, evidence, scope, rejections, source hashes, and publication destinations in versioned local learning records. Deliver behavior through portable skills and small native instruction sections. Active skill environments receive no aggregated profile overlay.

Review the entire consented library. Update relevant procedures and descriptions. If no existing workflow fits, create an instruction-only skill. Preserve unrelated text, supporting resources, permissions, and invocation settings. Supported changes to authorized user skills can apply automatically. Conflicts and uncertain technical claims stay pending. Third-party packages receive local companions.

A mandatory baseline carries universal guidance. Native sections load it and route tasks to applicable skills. Necessary standalone facts stay in scoped native context. The baseline and the native sections have separate 4 KiB limits. Overflow is visible. It never silently truncates evidence.

Keep global, remote-owner, and repository scopes distinct. Publish repository skills only to registered matching repositories. Skill files, native sections, and publication records form one reversible revision. Pending publication survives a completed capture batch.

## Memory and migration

Read consented Claude memory for registered repositories. Use source hashes to avoid processing the same memory again. Native memory stays read-only. Temporary task state does not become durable guidance.

Migration shows a preview by default. Before you switch delivery, do these steps:

1. Freeze the original library and instructions.
2. Map active profile entries and references.
3. Record unresolved scopes.
4. Validate coverage.
5. Publish successfully.

Keep legacy profiles for recovery. Source consent alone does not authorize skill writes.

Context diagnostics, hooks, MCP, dispatch, optional subagents, and repository setup use the shared skills delivery path. The [preference study](027-preference-study.md) evaluates the resulting delivery.

## Tradeoffs

Skill selection becomes part of correctness and needs separate delivery checks for each provider. Updating coherent workflows avoids creating one overlapping skill per correction. Automatic publication requires evidence, fingerprints, and reversible revisions. Unresolved scopes can stay pending.

Private learning records and evaluation evidence stay outside the public checkout. Bundling must also avoid embedded build-machine paths. Bind bundled TypeScript paths at runtime. Verify that the relocated package can still parse TypeScript.

## Verification

Cover updates and creation, baseline routing, memory idempotency, scope, consent, redaction, resource preservation, symlinks, conflicts, interrupted publication, and undo. Keep original and maintained evaluation libraries distinct. Native delivery probes use synthetic sessions. Successful migration alone is not evidence of better agent behavior.

Before you check execution support, validate the focused test paths and existing runtime directories. Unsafe links fail on every platform. On unsupported platforms, a valid snapshot stays unverified. Shadowclone creates no runtime directory and starts no process.

## Publication quality

A new draft can contain a complete skill document even when the request asked the model for the body. Parse that document with the existing skill parser. Then render the metadata once. Keep the body and the existing invocation settings. Ambiguous metadata needs review. Store the validated description with every published artifact. Refresh stale routing metadata during synchronization, also when the skill bytes have not changed. Native routing keeps its 4 KiB limit and its manual sections.

Review overlapping workflows across the entire applicable library. This includes third-party packages and global skills available in a repository. Find overlap in bounded catalogs, then compare the full redacted documents. Cache completed review work by input fingerprints. Resume within the existing learning budget. Conflicts become review proposals. Each proposal has both sources, the exact conflicting passages, and the decision to make. A conflict proposal never chooses precedence. It never edits either skill automatically.

Attach routing and drafting decisions to individual learning keys. A blocked shared draft leaves the skill unchanged. It names the records that block the others. Model prose and stale status alone cannot authorize retirement. Explicit retirement provenance stays separate from pending revisions or contradictions.

Explain missing scope, candidate evidence, conflicting evidence, and publication backlog separately. Organization guidance without a matching registered repository stays scoped and deferred. A feature request is not automatically a standing preference, and a dated product fact is not automatically obsolete. Uncertain classifications keep their evidence for review.

Implement in this order:

1. Document rendering and routing.
2. Keyed decisions and scope diagnostics.
3. Whole-library conflict review.

Verify these boundaries with synthetic fixtures, failed-before-fix regressions, budget exhaustion and retry, manual ownership, and the full repository gate. Test native routing through a synthetic Git repository. Then quality regressions do not depend on changes to the evaluation harness. Frozen evaluation environments and private receipts stay unchanged. Evaluate repaired environments as separate revisions.
