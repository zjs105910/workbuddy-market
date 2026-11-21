---
name: no-comments
description: "Spawn Comment Sicko, fix accepted findings, and offer encodings for claimed constraints."
disable-model-invocation: true
---

# No comments

Spawn Comment Sicko. Act on accepted findings.

Defer to Comment Sicko's fresh perspective.

## Scope

This skill edits files and delegates edits. A caller working under a read-only instruction never runs it and spawns no Comment Sicko, whatever its role label. It reports the comments it would flag as findings in its own read-only report, per [the runtime's Permissions section](../pstack-runtime/SKILL.md#permissions). Step 1's `role: "review"` is a label and does not make Comment Sicko read-only.

Use the caller's files or diff. Otherwise use the current diff against the base branch, default `main`, including the working tree.

[The runtime's Modes section](../pstack-runtime/SKILL.md#modes) sets the mode lines of every brief this skill writes and how its spawns run in light mode.

## Steps

1. Resolve the Comment Sicko reviewer on the `judgment and prose` role. Run `python3 <pstack-runtime>/scripts/roles.py show --cwd "$PWD" --parent "<inheritedProviderInstanceId>/<inheritedModel>" --role "judgment and prose"`. Set `target` to that seat, or omit `target` when the seat is `inherit`. If `delegate_task` rejects the target, apply the runtime's fallback and say which seat changed and why. Spawn Comment Sicko as a fresh child with `delegate_task` (`role: "review"`, `title: "Comment Sicko: <scope>"`, that `target`). Paste the body of [the Comment Sicko persona](../pstack-runtime/agents/comment-sicko.md) (everything after its frontmatter) at the top of the brief, then the scope as exact paths or the base ref and diff command. Do not restate its rules. The child sees none of this conversation, so the scope is the whole brief after the persona. It edits comments in the shared checkout, so run it alone: no other writer touches the scoped files until its report lands. Use `mode: "wait"` when step 2 is the next thing to do, otherwise `mode: "async"` and collect it per [the runtime's Delegation step 5](../pstack-runtime/SKILL.md#delegation).
2. Inspect its report and diff. Reject application-code edits, scope escapes, exception-protected deletions, misstated `MUST KILL` reasons, and flags that treat kept intentional code as guilty. Reshape flags on our-code surprises stay actionable. Do not restore those comments. A keep survives only with proof it is about something we cannot change. Audit missed scoped lint and TypeScript suppressions. Correctness or safety suppressions stay actionable `MUST KILL`s. Restore deletions only with exact exceptions and scoped proof. Before accepting thin `IMPORTANT` or `do not remove` kills or keeps, run `/how` or `/why` on their symbol. If a kill is ambiguous, do not restore. If a keep is refuted or still ambiguous, delete it. Revert and rerun one rejected report with the failure named. Reject a second, report it open, and fail `/no-comments`.
3. Fix trivial accepted flags directly by deleting a dead path, dropping a parameter, or using the real API. If any fix needs a shape, run `/architect` once for the accepted set and surrounding code. Stop at the sketch. Architect shapes. Step 4 implements.
4. Implement the smallest root-cause fix in scope. Remove every named workaround. If the root cause is out of scope, land the smallest in-scope fix and report the rest open. The **principle-fix-root-causes** and **principle-redesign-from-first-principles** skills guide intent only. Neither authorizes widening the fence nor fixing instances outside it. Never bolt on symptom guards.
5. Constraint comments say `do not remove`, `do not change wording`, or `talk to X before changing`. Leave keeps about things we cannot change. Offer the cheapest in-scope type, runtime, test, or CI lint. Wait for interactive approval. Unattended and eval require caller pre-approval. If approved, encode then delete. Otherwise delete, report the constraint open, and sketch out-of-scope work.
6. Report the deletion count, restored comments, reruns, architect sketch, fixes, encoding offers, encodings, unenforced constraints, and other open work.
