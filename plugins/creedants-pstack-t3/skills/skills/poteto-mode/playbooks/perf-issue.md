### Perf issue

**You own the measurement story. Plan, review, verify the numbers.** Tie every fix to a measurement, don't read source instead of measuring.

[The runtime's Modes section](../../pstack-runtime/SKILL.md#modes) sets the mode lines of every brief this playbook writes and how its spawns run in light mode.

1. Capture a baseline trace via the matching control skill. Vet the baseline, and each later number, with the **benchmark-checklist** skill.
2. `how` to ground hypotheses. Don't claim a perf ceiling without running it first.
   Try the performance mantras in order, cheapest first:
   1. Don't do it. Stop work whose result nothing uses rather than cheapening it.
   2. Do it, but don't do it again.
   3. Do it less.
   4. Do it later.
   5. Do it when they're not looking.
   6. Do it concurrently.
   7. Do it cheaper.

   When an earlier mantra meets the target, stop.
3. Plan the fix from the trace. If it crosses a function boundary, `architect` first. Delegate implementation to a child task on the `perf-issue` role, resolved per [the runtime's Roles section](../../pstack-runtime/SKILL.md#roles). Write its brief per step 4 of [the runtime's Delegation section](../../pstack-runtime/SKILL.md#delegation): the poteto-agent persona first, the lines `roles.py mode --playbook perf-issue --attempt <kind>` prints, which start with `Playbook: playbooks/perf-issue.md`, and `roles.py check-brief` before `delegate_task`. Collect the delegate per [the runtime's Delegation step 5](../../pstack-runtime/SKILL.md#delegation). Review the diff. Capture a post-fix trace.
   Apply the **sequence-verifiable-units** principle skill, verifying each attempt before trying the next.
4. Parse and compare the artifacts (JSON to sqlite, diff). "Inconclusive" or wrong-surface is not a pass. Flag it.
5. Cite the measurement in the PR.
6. Run **Opening a PR**.

For sustained improvement against a metric rather than a one-off fix, use the Hillclimb playbook (`playbooks/hillclimb.md`).

**Reply:** baseline number, post-fix number, delta, artifact path.
