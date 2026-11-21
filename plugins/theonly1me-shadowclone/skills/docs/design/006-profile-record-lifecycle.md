# Stable profile records

This defines the legacy profile lifecycle. Active environments now publish [skills](023-skills-as-delivery.md), but migration still needs to interpret these records.

## Problem

Content-derived identities changed each time someone reworded a rule. Learning could duplicate an edited rule or restore one that the user had deleted. Confidence values also mixed the strength of the evidence with the decision to deliver the guidance.

## Decision

Give generated rules a stable key that does not depend on their wording. Store source, evidence, scope, conditions, and lifecycle state explicitly. Compilation uses the lifecycle decision. It does not infer activation from confidence.

Keep a ledger of the last generated text. Compare that text with the current file to tell an untouched rule, a user edit, and a deletion apart. Preserve edited rules as user-owned guidance. Keep rejection or retirement records, so a later learning pass cannot silently recreate deleted guidance.

Keep a published rule active during review of contradictory evidence. A proposal is separate from the user's current instruction. [Automatic preference learning](015-automatic-preference-learning.md) later refined the historical activation thresholds. Explicit durable steering can qualify from one session. Inferred behavior needs independent support.

## Compatibility and verification

Import older profile formats without discarding manual text. Malformed or ambiguous files must block destructive rewriting. Check stable identity across wording changes, repeated imports, edits, deletions, rejected proposals, and compilation of active guidance. A migration must preserve both the visible text and the user's decisions about it.
