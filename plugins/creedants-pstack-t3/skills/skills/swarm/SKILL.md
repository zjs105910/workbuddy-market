---
name: swarm
description: "Fan out N parallel workers, drain them, and return one report. Use for /swarm, 'swarm this', or parallel coverage, races, gauntlets, and exploration."
---

# Swarm

Read [the pstack-t3 runtime](../pstack-runtime/SKILL.md) before spawning workers, choosing models, scheduling, or isolating work. It maps those steps onto T3's orchestrator tools.

Fan out N parallel child tasks. They may cover separate slices, race the same brief, or mix both. The parent waits, aggregates, and returns one report.

[The runtime's Modes section](../pstack-runtime/SKILL.md#modes) sets the mode lines of every brief this skill writes and how its spawns run in light mode.

## Start

Open a todolist with one entry per phase before launching anything.

1. Frame
2. Fan out
3. Aggregate
4. Report

## Phase A: Frame

1. State the done predicate and the artifact or report the swarm must return.
2. Choose the shape. Partition into slices, race N workers on identical briefs, or mix both. For a race or mixed shape, declare `first pass`, `rank all`, or `best-of` before spawning.
3. Set N from the user or derive it from the shape. N is total workers, not a concurrency limit.
4. Pick the worker model from the `swarm workers` role. Call `orchestrator_capabilities`. Paste that tool result into this quoted heredoc. If the catalog result is large, save it to a temporary file with the host's file tool and pass that path to `--catalog`.

```bash
python3 <pstack-runtime>/scripts/roles.py show --cwd "$PWD" --catalog - --parent "<inheritedProviderInstanceId>/<inheritedModel>" --role "swarm workers" <<'JSON'
<the orchestrator_capabilities JSON>
JSON
```

The quoted heredoc sends the JSON unchanged. The command does not write the catalog into the repository, and parallel children do not share a file. It resolves the `swarm workers` role per [the runtime's Roles section](../pstack-runtime/SKILL.md#roles). Every worker uses that seat. An `inherit` seat means omit `target` so the workers run on the parent model. If `delegate_task` rejects the target, apply the runtime's fallback and say which seat changed and why. For a model race, name each arm's target up front from `orchestrator_capabilities`, and report whether the arms' models actually differed.

5. Give each worker its own writable output when it writes. A worker that writes to the repo while another writer may overlap gets its own git worktree per [the runtime's Isolation section](../pstack-runtime/SKILL.md#isolation). When workers verify or measure commits, each brief names the exact SHAs. A measurement brief also names the method (sample count, what one sample is, order). The worker records both in its result.

## Phase B: Fan out

Spawn all N workers in one message, one `delegate_task` call per worker, with `mode: "async"`, `role` `general` (or `review`, `research`, or `test` when the slice is only that), the step 4 `target` (omitted for `inherit`), and a stable `clientRequestId` such as `swarm-<slug>-<n>`. Retain every returned `taskId` in the todolist. Workers are local child tasks, so they can reach files, browsers, and auth on this machine.

When a worker must start from a non-default branch, name that branch in the brief as the worktree's base. Uncommitted changes do not reach a new worktree, so commit or push first.

Every brief stands alone. Include the goal, scope, exact slice or race arm, how to verify, and what to report. A worker that only reads gets a read-only brief that says "do not edit files, commit, or push." A worker that writes code for a poteto-mode playbook also follows step 4 of [the runtime's Delegation section](../pstack-runtime/SKILL.md#delegation): the poteto-agent persona first, the lines `roles.py mode --playbook <name> --attempt <kind>` prints for the playbook it serves, which start with `Playbook: playbooks/<name>.md`, and `roles.py check-brief` before `delegate_task`. Reports use `PASS`, `ISSUES`, or `BLOCKED` with evidence. A worker that can prove a defect reports `ISSUES` and lists every issue it can prove, not only the first.

If a worker drops out, proceed with N-1 and note it.

## Phase C: Aggregate

Collect each worker's result per [the runtime's Delegation step 5](../pstack-runtime/SKILL.md#delegation). Read the terminal results. Drop a result that does not record the SHAs and method its brief names, and respawn that worker once as a fresh child. After a second miss, record a gap. A gap does not count as a pass. For coverage, every required slice needs a result. For a race, apply the selection rule declared up front. Use first pass, rank all, or best-of. Do not paste raw worker dumps.

Keep a compact result table, one-line evidenced issues, and explicit gaps or dropouts. Remove worker worktrees after integrating them.

## Phase D: Report

Return one consolidated in-chat report with the table, issue one-liners, gaps or dropouts, any seat that fell back, and the race rule when used.
