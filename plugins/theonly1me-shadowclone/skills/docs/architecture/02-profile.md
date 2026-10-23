# Learning and skill delivery

Durable learning is stored in `~/.shadowclone/environment.json` and published into skills and native instructions. Claude Code and Codex receive short rules inline and select detailed skills by name, with no unconditional baseline file read.

## Evidence and reconciliation

Learning records keep guidance, scope, observations, source hashes, rejection state, and publication destinations. Evidence stays apart from the instruction budget, so a failed publication does not lose it.

Reconciliation uses redacted user steering as evidence and bounded agent text as labeled context. Context alone never supports a rule. Current source consent filters indexed events, and each reference is checked again before it resolves. Explicit durable guidance can activate after one session. Inferred behavior needs three independent sessions. Questions, silence, temporary exceptions, and interruptions alone make no preference. Contradictory evidence creates a review decision and never silently replaces an explicit instruction.

Manual deep learning and background learning call `packages/learning/src/learning/service.ts`. `storage.ts` in that folder selects environment persistence and keeps the legacy-profile fallback at one compatibility boundary. A declined manual proposal is stored with source provenance in `learning-pending.json`. Approval checks current consent and publishes only the selected keys. It does not repeat extraction or enable automatic maintenance. `remember` stores a direct preference without inference.

## Publication

The planner searches the consented library for a matching workflow, reads selected skills through redaction, and proposes exact section edits. If no workflow fits, it can create an instruction-only skill. Unrelated text, invocation settings, resources, and conditional requirements stay intact.

Each draft returns an outcome for every learning key. A pending outcome blocks the shared draft, and other records name the blocking keys. Only a recorded retirement request removes stale guidance.

The baseline skill holds universal guidance and is not read before every task. Task skills hold procedures, and short scoped rules appear in native context. The baseline and each native section have a 4 KiB ceiling, and a skill has 48 KB and 500 lines. Overflow keeps its evidence.

An update reviews overlapping workflows across the full library, even without new learning. Bounded catalog batches pick candidates for full-document comparison through the redaction boundary, and a conflict must quote exact supporting passages. Local fingerprints cache finished review work within the learning budget. A conflict proposal records both sources and the precedence decision it needs, never edits either source, and a source change supersedes it. See [skill maintenance](../guides/skills.md).

One revision groups skill files, resources, native instructions, and evidence decisions. Fingerprints detect intervening edits, failed writes roll back, and undo refuses later conflicts.

## Scope and ownership

Global output holds global learning only. Project output needs a registered repository with verified Git identity. A past directory gets a remote identity only after a reviewed association. Organization guidance stays within its remote-owner scope. Imported repository instructions stay evidence and are not republished. See [enterprise controls](../guides/enterprise.md#scope).

Copies of a skill keep supporting bytes and executable permissions. One manual edit can sync, and divergent edits stay conflicts.

Sync regenerates native sections in the same revision and keeps manual sections. Routine sync creates no shared `AGENTS.md` or `CLAUDE.md` in a repository. A local install uses private Claude and Codex destinations, and shared files come from reviewed repository setup. A description that exceeds routing capacity stays a review decision and keeps the existing native section.

## Builds, memory, and compatibility

Terminal and browser builds publish through the same revision machinery. Recurring Claude memory extraction needs the named source and a registered, matching repository. Memory is read-only, hashes skip unchanged notes, and temporary task state does not become durable guidance.

Migration freezes original skills and native instructions, keeps legacy learning, and publishes in bounded batches. Delivery switches only after coverage and file validation. Legacy profile files stay as recovery artifacts ([migration](../guides/migration.md)).

Hooks, subagents, and MCP use the active delivery path. `shadowclone_context` returns scoped routing, and `shadowclone_profile` is a deprecated alias. The [preference study](../../evals/README.md) compares original and maintained libraries in separate arms.
