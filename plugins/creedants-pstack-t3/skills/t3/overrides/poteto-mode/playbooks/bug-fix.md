### Bug fix

**You own this task. Plan, review, verify.** Delegate investigation and the fix to subagents, stay in the lead.

[The runtime's Modes section](../../pstack-runtime/SKILL.md#modes) sets the mode lines of every brief this playbook writes and how its spawns run in light mode.

Be scientific. Every shipped line traces to runtime evidence. Belt-and-suspenders that "might help" is a hypothesis, not a fix. It does not ship. When evidence refutes a hypothesis, revert what it motivated. The smallest change the evidence justifies ships, nothing more.

1. Reproduce it yourself on the matching surface via the control skill (Non-negotiables), even when a debug or instrumentation protocol says to ask the user to reproduce. Ask the user only with a stated, specific reason the control surface cannot reach the target, and only after driving it as far as it goes. If it won't reproduce directly, synthesize the trigger, tighten conditions, or instrument until it fires.
2. Binary-search the cause. Form the candidate hypotheses, then rule them out until one survives. Seed them with `how` over the affected subsystem and the **why** skill for regression history. Each pass, take the split that cuts the most remaining problem space, get runtime evidence, eliminate. When program state is unclear, add instrumentation or logging and read it as the code runs. Don't guess. Drive a long or stubborn hunt as an explicit loop in the session, one split per iteration. When each pass waits on something slow (a soak, a nightly job), hold the hunt with `schedule_task` per [the runtime's Scheduling section](../../pstack-runtime/SKILL.md#scheduling) and delete the schedule when one hypothesis survives. Confirm the surviving *mechanism* with runtime evidence before the step-3 architect/interrogate fan-out.
3. Plan the fix. If it crosses a function boundary, `architect` first. Delegate implementation to a child task on the `bug-fix` role, resolved per [the runtime's Roles section](../../pstack-runtime/SKILL.md#roles), with a specific scope. Write its brief per step 4 of [the runtime's Delegation section](../../pstack-runtime/SKILL.md#delegation): the poteto-agent persona first, the lines `roles.py mode --playbook bug-fix --attempt <kind>` prints, which start with `Playbook: playbooks/bug-fix.md`, and `roles.py check-brief` before `delegate_task`. Collect the delegate per [the runtime's Delegation step 5](../../pstack-runtime/SKILL.md#delegation).
4. Verify on the same surface. The original repro now passes. "Inconclusive" or wrong-surface is not a pass. Flag it. Unit tests show branch behavior, not bug absence.
5. Stage the commits so the failing repro lands before the fix in git history. See the **tdd** skill for the failing-test-first cadence when the bug has a cheap local test path. Skip it when the test would be expensive, integration-heavy, or unclear.
   This is the canonical **sequence-verifiable-units** principle skill, the failing test first and the fix on top.
6. Run **Opening a PR**.

**Reply:** what was broken, root cause, fix, how you verified. Paste failing-then-passing repro output verbatim.
