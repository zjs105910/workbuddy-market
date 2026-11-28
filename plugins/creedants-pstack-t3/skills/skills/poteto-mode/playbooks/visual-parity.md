### Visual parity

**You own pixel-exact equivalence. The baseline is the spec. You do not touch it.** Equivalence is verified by image diff, not by eye.

[The runtime's Modes section](../../pstack-runtime/SKILL.md#modes) sets the mode lines of every brief this playbook writes and how its spawns run in light mode.

1. Establish the baseline first, before any migration: a visual regression harness that screenshots the current component across its states, plus the target when matching two implementations. No baseline, no parity claim. A blocking prerequisite, not a follow-up.
2. Anti-shortcut clauses, stated and held: no harness modifications, no baseline tampering, no component restructuring to make a diff pass. If the baseline looks wrong, stop and ask, don't edit it.
3. Migrate one component at a time. Parallelize across worktrees, one owner child task per component, each in its own worktree per [Isolation](../../pstack-runtime/SKILL.md#isolation) (the **separate-before-serializing-shared-state** principle skill). Shared primitives migrate first as a blocking phase.
4. Verify each component against its baseline via image diff on the matching surface via the control skill, or T3's preview tools when no control skill is installed (`preview_open`, `preview_resize`, then `preview_snapshot` with `save: true` for the PNG to diff, per [Verification surfaces](../../pstack-runtime/SKILL.md#verification-surfaces)). A nonzero diff is a fail. Investigate the pixel delta. Loop explicitly per component in the session until the diff is zero. Hold a loop that outlives the session with `schedule_task` per [Scheduling](../../pstack-runtime/SKILL.md#scheduling), and delete it at zero diff.
5. Run **Opening a PR** per component or per safe batch.

**Reply:** components migrated, the diff result for each, the baseline harness location, what's left.
