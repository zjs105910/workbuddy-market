---
name: pstack-runtime
description: How pstack-t3 skills delegate, pick models, isolate work, schedule, and verify inside T3 Code through the orchestrator V2 tools. Read before running any other pstack skill that spawns workers, picks a model, or schedules work.
---

# pstack-t3 runtime

pstack-t3 runs inside T3 Code. Every provider T3 drives (Claude, Codex, Grok, Cursor, Pi, OpenCode, Muse, ACP agents) gets the same `t3-code` MCP server. This file maps each pstack concept onto those tools, so a skill works the same whatever model runs it.

Tool names may carry a harness prefix, such as `mcp__t3-code__delegate_task` or `mcp__t3_code__delegate_task`. The semantics are the same. If a T3 tool this skill names is not in your tool list, find it with the host's tool search when the host has one, and call it by the name the search returns. When the host has no tool search, call the tool directly. Start with `orchestrator_capabilities`, and do not conclude the tools are missing until a search or a direct call has failed. ACP agents that cannot see the tools use the terminal bridge in [ACP fallback](#acp-fallback).

## Vocabulary

| pstack says | In T3 |
| --- | --- |
| subagent, worker, delegate, reviewer, runner, judge | A child task created with `delegate_task`, owned by this thread. |
| cloud worker | A child task. T3 children run on this machine, so they can reach local files, browsers, and auth. |
| background, `run_in_background` | `delegate_task` with `mode: "async"`. |
| wait for a worker | A thread with a schedule of its own ends the turn, and its completions wake it. Any other thread keeps a bounded wait with `t3_thread_wait`. Call `task_status` for a result mid-turn. See [Delegation](#delegation) step 5. |
| cancel a worker | `task_cancel`. |
| model slug, role model | A target `{providerInstanceId, model, options}` from `orchestrator_capabilities`, resolved through roles. See [Roles](#roles). |
| `inherit-parent`, `auto` | `"inherit"`. Omit `target` so the child inherits this thread's provider, model, and options. |
| separate chat, coordinator chat, PR owner thread | A top-level thread from `t3_thread_launch`, only where [Top-level threads](#top-level-threads) allows it. |
| worktree for a worker | A git worktree the child creates for itself, or a `t3_thread_launch` worktree binding for top-level threads. See [Isolation](#isolation). |
| `/loop`, hourly tick, automation, scheduled wakeup | `schedule_task`. See [Scheduling](#scheduling). |
| `scripts/watch-pr`, a poll loop, waiting on CI | `watch_pull_request` on the thread that owns the PR. See [Pull request watching](#pull-request-watching). |
| transcript, chat history, cloud-agent URL | A T3 thread, read with `t3_thread_search` and `t3_thread_read`. |
| control-ui, browser MCP | T3 preview tools: `preview_open`, `preview_snapshot`, `preview_click`, `preview_type`, `preview_evaluate`, `preview_recording_start`. Use `preview_hover` to reveal a menu or tooltip, `preview_drag` to drop one element on another, `preview_select` to choose an option in a native select, `preview_upload` to give the page files, and `preview_dialog` to accept or dismiss a browser dialog. |
| ask the user (`AskQuestion`) | The host's question tool if it has one, otherwise a short question in the reply. |
| todolist | The host's todo tool if it has one, otherwise a checklist in the work log. |
| PR you opened or now drive | Register it with `link_pull_request`. |
| status page, dashboard, report table, chart | A page published with `html_preview`, then `html_render`, inside a reply already due. See [Visual reports](#visual-reports). |

## Deadlines

A deadline or timebox sets the order of work. It never waives a step. This holds for Autopilot's early red-test-and-PR target, a brigade or Orchestrate timebox, and any "aim for N minutes" in a brief. Start the deliverable the deadline names first, then run every step the playbook prescribes before the next gate, such as `CODE-READY` or the final report. That includes How, Architect, investigation, and the code delegate. The clock is never a `skip:` reason. When the remaining steps cannot fit, stop at a verifiable point and report the steps that remain instead of skipping them. A step that the brief's `Waived by mode:` line names is not a skip, because the mode removed it before the attempt started.

## Delegation

1. Call `orchestrator_capabilities` once per session before the first delegation, and again after a delegation fails on a target. It returns `parentThreadId` (this thread's own ID, for `t3_thread_read` on yourself), `inheritedProviderInstanceId` and `inheritedModel` (this thread's own seat), `providers[]`, each with `providerInstanceId`, `models[]` and their `options`, `canRunChildTask`, `canRunCrossProviderChildTask`, and `constraints`. Treat a provider with `canRunChildTask: false` as unavailable and report its `constraints` if a role needed it.
2. Resolve the role's targets per [Roles](#roles).
3. Spawn every independent child in one message:

   ```json
   {
     "task": "<self-contained brief>",
     "title": "<role>: <slice>",
     "role": "review",
     "mode": "async",
     "target": {"providerInstanceId": "claudeAgent", "model": "claude-opus-5-5", "options": {"effort": "xhigh"}},
     "clientRequestId": "<skill>-<slug>-<seat>"
   }
   ```

   - `role` is one of `implementation`, `research`, `review`, `design`, `test`, `general`.
   - Omit `target` for an `inherit` seat.
   - After a `t3_thread_launch` or `delegate_task` call whose seat has `options`, read the applied options from the launch result's `modelSelection.options` or from `t3_thread_configuration` on the child's `childThreadId`, and never call again with the options removed. Each applied option is one object `{"id": <key>, "value": <value>}`. A missing option or a different value is a mismatch. On a mismatch, or when the call is refused for its `options`, stop that child. Report the tool's error text. Call `task_cancel` for a child task. Call `t3_thread_interrupt` and then `t3_thread_wait` for a thread. A Cursor harness sent `options` as a string, T3 refused the call, and the child then dropped the options.
   - OpenCode moves a long command to the background, tells the model to end its turn, and resumes the thread when the command finishes. T3 publishes the task's result when the first turn ends, and the later turn does not reopen the task. Paste this paragraph unchanged into the brief of every child seated on OpenCode.

     > Nobody resumes you after your turn ends, so a command left running in the background is lost. Run every long command in the foreground with a long enough timeout, for example a bash timeout of 600000 ms. If your shell moves a command to the background anyway, keep checking its output, with `sleep 60` between checks, until it finishes. Do not end your turn until your report is written.

     When an OpenCode child's task is terminal and the report file its brief named is missing, the task is not finished. Read its activity with `t3_thread_read`. While a later turn on its thread still runs, wait on it per step 5. Otherwise handle it per [Failure handling](#failure-handling).
   - Use a stable `clientRequestId` so a retried call does not spawn a duplicate.
   - Retain every returned `taskId` in your todo list or work log.
4. A child starts with only its brief. It sees none of this conversation. Put the goal, the exact paths or SHAs, how to verify, and the report shape in the brief. Point at files instead of pasting large context. Write tool steps as plain verbs ("read", "search the repo", "run"), because the child may be a different provider with different tool names. When the role entry `roles.py show` printed for the child's seat has `haikuBrief`, paste its paragraphs unchanged, in order, at the end of the brief, per [Claude Haiku 5.5](#claude-haiku-55). A code-writing child inside a poteto-mode playbook opens with the poteto-agent persona body. Below it, paste unchanged the lines `python3 <pstack-runtime>/scripts/roles.py mode --cwd "$PWD" --playbook <name> --attempt <kind> [--brief-mode <value> | --session-mode light]` prints, per [Modes](#modes). They start with the `Playbook: playbooks/<name>.md` line, such as `Playbook: playbooks/feature.md`, and carry the required `Mode:` line. Write no `Playbook:` line of your own, because a second one fails the check. The lines include `Attempt:`. Under `Mode: light` they also include any `Waived by mode:` line. Under `Mode: full` there is no `Waived by mode:` line, and the brief must not add one. Copy the printed `Mode:` value into `--brief-mode` on the `roles.py show` call that seats the delegate, and pass no other mode flag. Write that brief to a file and run `python3 <pstack-runtime>/scripts/roles.py check-brief <file>` before `delegate_task`. Exit 1 names what is missing. Fix the brief, run the check again, and pass the checked text unchanged. A seat that matches this thread's model, or an edit that looks small, is not a `skip:` reason for the code delegate.
5. Collect results.
   - If nothing else in this turn depends on the results, and this thread has a schedule of its own that wakes it, end the turn. Each completion wakes this thread.
   - A completion arrives only when the child's run ends. A child stalled on an approval request, or a run that stays open after its final message, never ends, so no wake comes. A thread with no schedule of its own, such as a worker running a brief, does not end its turn while a child is open. This holds even though the `delegate_task` tool text says to end the turn. A coordinator's liveness check is not this thread's schedule. Call `t3_thread_wait` on the child's `childThreadId` with `timeoutMs: 300000`. When it returns a terminal status, call `task_status` to read and acknowledge the result, because `t3_thread_wait` does not acknowledge it. When it returns `timedOut: true`, read the child with `t3_thread_read`, `view: "activity"`, and `afterPosition`. A child with no new item for 10 minutes is stalled. Handle it per [Failure handling](#failure-handling), then wait on the next open child.
   - A child with a final assistant message that holds the result the brief asked for, no pending tool or child run, and no new activity for two minutes is stalled. A message that says more work follows does not hold the result. A last message that says the child waits on a background command does not hold the result either, so this two-minute rule does not apply to it. After you see that message while the child's run is still open, call `t3_thread_wait` on the child's `childThreadId` with `timeoutMs: 120000`. Then read its activity again and call `task_status`. Handle it per [Failure handling](#failure-handling) only when the wait timed out, `workState` is still `working`, that message is still the last item, and no tool or child run is pending. Otherwise the 10-minute rule above decides that child.
   - A child's run can end while its task stays open. A Claude child that leaves a background shell job running is one case. Then `t3_thread_wait` on its `childThreadId` returns at once, because an idle thread returns immediately, while `task_status` still reports `working` or `waiting_for_children`. Do not repeat that call. Wait with `t3_thread_wait` and `timeoutMs: 120000` on another open child whose run is still going. With none, wait on this thread's own run. Read the `activeRunId` of the `parentThreadId` from `orchestrator_capabilities` with `t3_thread_read`, and pass them as `threadId` and `runId`. Without `runId`, the call picks this thread's latest run, which can be a queued run already cancelled, and returns at once. This thread's run stays open during the call, so it returns `timedOut: true` after 120 seconds. Never wait with a shell `sleep`, which some harnesses refuse. After each wait, read the child with `t3_thread_read`, `view: "activity"`, and `afterPosition`, then call `task_status`. Count 10 minutes from the child's last activity item. A new item restarts the count, and a `task_status` check does not. A child with no new item for 10 minutes is stalled, even when its last message holds the result, because the two-minute rule above needs an open run. Handle it per [Failure handling](#failure-handling). When its run starts again, go back to the waits above.
   - If you need a result now, call `task_status` with the `taskId`. Reading a terminal result this way acknowledges it, so no completion notification follows. Process that result immediately, as if the notification had arrived. `workState: "result_available"` means done, and `summary` holds the result. `working` and `waiting_for_children` mean not done. `hasPendingChildRuns` does not change that. See [Failure handling](#failure-handling). Do not busy-poll. Do other work between checks.
   - `mode: "wait"` blocks for at most `timeoutMs`, ten minutes by default. Use it only for short children whose result gates the very next step. `waitTimedOut: true` does not cancel the child. Keep the `taskId`.
6. You own every child's output. Read the diff or the evidence yourself before you report it. A child's "done" is a claim, not a verification.

Same-provider native subagent tools (Claude's Agent tool, Codex's subagents) are fine for an `inherit` seat when they run the parent's model. Use `delegate_task` for every other seat, including same-provider seats on another model. Never substitute a top-level thread for a child task.

### Permissions

Children inherit this thread's runtime mode and interaction mode. Omit `runtimeMode` so the child inherits. Never raise it above the parent's, and never lower it. A child in `approval-required` stops at its first command on an approval request that no tool can answer, so it never finishes. A read-only reviewer is a read-only brief: say "do not edit files, commit, or push" in the task. T3 has no read-only flag that keeps MCP access, so the brief carries the constraint. Muse supports only `approval-required` and `full-access`. Under any other parent mode T3 runs a Muse child or launched Muse thread as `approval-required`, so it stalls at its first command. Read `runtimeMode` from `orchestrator_capabilities` before you seat Muse. Under a mode Muse lacks, replace the Muse seat with `"inherit"` per [Fallback](#fallback) and say why.

### Failure handling

- A target is rejected: call `orchestrator_capabilities`, then fall back per [Roles](#roles), and say which seat changed and why.
- A child fails or returns nothing usable: proceed with N-1 and record the dropout. Respawn once with a fresh child for a required slice. Never resume a failed child to fix its own work. When the failure carries a provider error, follow the next bullet before that respawn. A failure that reads `Killed: out of memory.` is an out-of-memory kill that T3 reports. Lower the load before you respawn that child. Run fewer children at once, or run builds through the slot in [Local command capacity](#local-command-capacity). Report a second kill as a blocker.
- Check a usage limit only for a failed child that did not return the brief's result. Read the error text from `task_status` `summary`, or from the last activity item of `t3_thread_read`. Run this command with that text on stdin. Pass `--cwd`, `--parent`, the catalog file, and the mode flag the same way as `show`. Pass `--role`, `--provider`, `--model`, and `--options` from the failed seat. For a reviewer role, repeat `--author` for every model that wrote the diff, per [Gate review](#gate-review): each code delegate's model, and the worker's model when the worker wrote code. A `review backups` member needs the same `--author` flags when it runs with `--resume`. Repeat `--out` for each provider already tried. The command prints `relaunch`, `panel`, `park`, or `not-usage-limit`.

  ```bash
  python3 <pstack-runtime>/scripts/roles.py backup --cwd "$PWD" --catalog <file> --parent "<inheritedProviderInstanceId>/<inheritedModel>" --role "<name>" --provider "<providerInstanceId>" --model "<model>" [--options '<json>'] [--author "<providerInstanceId>/<model>" ...] [--out "<provider>" ...] [--resume] [--brief-mode <value> | --session-mode light] <<'TEXT'
  <the error text>
  TEXT
  ```

  On `relaunch`, start a fresh child on the printed seat. Give that child a new stable `clientRequestId` ending in `-backup`. Confirm the applied options per [Delegation](#delegation) step 3. On `not-usage-limit`, respawn per the bullet above. On `park`, launch nothing. A worker moves to `claude-opus-5-5` on `claudeAgent`. `how explorer`, `why investigators`, and `skill tests` move to `claude-sonnet-5-5` on `claudeAgent`. `verifiers`, `interrogate reviewers`, and `arena cross-judge pool` move to `grok-4.7` on `grok`, then `claude-opus-5-5` on `claudeAgent`, skipping every author's family. When every backup family is an author family, the command parks. Every family comparison in `roles.py` uses normalized model ids, per [Built-in defaults](#built-in-defaults). A panel seats each family once. For a `verifiers` seat with `review backups` set, the command prints `panel` instead. On `panel`, spawn one fresh read-only child per printed seat with the same gate brief and a stable `clientRequestId` ending in `-panel-<n>`. Confirm each seat's options per [Delegation](#delegation) step 3. Wait until every member is terminal, even after two pass. A member that hits its usage limit runs this command with `--role "review backups"`, which parks it, and it counts as no pass. A member resumed after a reset runs `--resume --role "review backups"` with every `--author`. Without `--author` the command exits 2. It parks a member whose family is an author's, and that member counts as no pass. A member that fails otherwise respawns once. Land only if no reviewer reproduces a blocker and at least two of the panel pass. With `review backups` unset, or fewer than two usable seats, the command prints `park`. Backup never selects Codex or Cursor. Codex stays the default reviewer. A limit on `claudeAgent` parks a worker. A Claude model on another provider, such as `cursor/claude-opus-5-5`, moves to `claudeAgent`. A panel relaunches the failed seat and says when a family repeats. `park` on a panel proceeds with N-1. The backup is one hop. A second limit passes both providers as `--out` and parks a worker. After the reset time the error named, run the command with `--resume`, the parked item's original seat, the same `--author` flags, and `--out` for each provider whose reset has not passed. `--resume` reads no error text. It prints the original seat when its provider is back, and otherwise the backup above, so a worker gets the `claudeAgent` backup. A reviewer seat still skips every author's family. Start a fresh child on that seat. A parked worker keeps its lease and its branch's work. Say the printed `report` line in your report.
- `hasPendingChildRuns` on `task_status` does not mean the child is still running. It reports later turns on the child's thread, even after the task ended, and it does not reopen the task, including a turn you start with `t3_thread_send`. Decide completion by `workState` alone. On T3 Code 0.0.46-nightly.20261008.2813 or later, a turn held in a stopped queue does not count, and startup recovery on that host repairs a task an older build left `working` behind a held queue.
- A stalled child (see [Delegation](#delegation) step 5): read its last items. When its last assistant message holds the result the brief asked for, use that message as the result and call `task_cancel` on the task. When its last item is an approval request that is still waiting, call `task_cancel` and respawn once with no `runtimeMode`. Otherwise call `task_cancel` and respawn once for a required slice.

### Fresh children by default

Give new work to a fresh child with consolidated scope: the original brief, every later directive, and the prior child's report and branch. Message an existing child thread (`t3_thread_send`) only when the new work strictly needs state that lives with it, such as uncommitted changes in its worktree or a dev server it runs.

A `t3_thread_send` to a child whose task has already published its result can start a separate task for that message. Read the send result for a `taskId`. When it carries one, retain it and collect that task per [Delegation](#delegation) step 5. Its `summary` holds the answer, and the original task's `summary` does not change. When the result carries no `taskId`, wait with `t3_thread_wait` on the `childThreadId` and read the answer with `t3_thread_read`.

## Roles

Roles let one skill run on whatever providers the user has. A role value is a list of seats. Each seat is `"inherit"` or a target.

### Where roles live

1. `.pstack/t3-roles.json` in the project root. A role here replaces the same role from the user file.
2. `~/.config/pstack-t3/roles.json`, or `$XDG_CONFIG_HOME/pstack-t3/roles.json`.
3. Built-in defaults below.

Print the merged roles for the current project with:

```bash
python3 <pstack-runtime>/scripts/roles.py show --cwd "$PWD" --parent "<inheritedProviderInstanceId>/<inheritedModel>" [--brief-mode <value> | --session-mode light]
```

When the brief this call seats has a `Mode:` line, replace the bracket with `--brief-mode <value>`. Copy that line's bare value, and pass no other mode flag. When the brief has no `Mode:` line and the session is light, replace the bracket with `--session-mode light`, except for a user's explicit reflect, which passes `--session-mode full`. Otherwise delete the bracket. A call with no mode flag takes its mode from the roles files.

Always pass `--parent` with the values from `orchestrator_capabilities`. The saved catalog records whichever thread ran setup, so it never names this thread. Without `--parent`, the verifier panel treats no seat as this thread's own, and `show` cannot settle an `inherit` seat on a thread that runs an excluded model. `show`, `validate`, and `write` reject a malformed `--parent`. See [Excluded seats](#excluded-seats).

`<pstack-runtime>` is the directory holding this file. It sits next to every other pstack skill directory, so from a skill at `<dir>/swarm/SKILL.md` it is `<dir>/pstack-runtime`. Add `--role "<name>"` for one role. The output is small JSON with `source` per role. It resolves against the catalog snapshot that `setup-pstack` saved, if any. A role that reports `"seats": "catalog-required"`, or an adaptive panel that reports `"seats": "default-panel"`, needs a catalog. Call `orchestrator_capabilities`. Paste that tool result into this quoted heredoc. If the catalog result is large, save it to a temporary file with the host's file tool and pass that path to `--catalog`.

```bash
python3 <pstack-runtime>/scripts/roles.py show --cwd "$PWD" --catalog - --parent "<inheritedProviderInstanceId>/<inheritedModel>" --role "<name>" [--brief-mode <value> | --session-mode light] <<'JSON'
<the orchestrator_capabilities JSON>
JSON
```

Do not reconstruct role defaults in the calling skill. Pass a file path to `--catalog` when the catalog is already a file. Setup does that. One temporary file feeds `show`, `write`, and the saved snapshot. Fill the bracket by the same rule as the first command.

### Role names

| Role | Seats | Used by |
| --- | --- | --- |
| `feature, refactoring` | 1 | Feature and Refactoring code delegates |
| `bug-fix` | 1 | Bug fix code delegates |
| `perf-issue` | 1 | Perf issue code delegates |
| `hillclimb` | 1 | Hillclimb experiment delegates |
| `judgment and prose` | 1 | Prose, judgment, briefs, synthesis |
| `hardest tasks` | 1 | Cross-cutting design, concurrency, subtle algorithms |
| `how explorer` | 1 | how |
| `how explainer` | 1 | how |
| `why investigators` | 1 | why, one seat model for every investigator |
| `why synthesizer` | 1 | why |
| `reflect tooling` | 1 | reflect |
| `reflect judgment, divergent, synthesizer` | 1 | reflect |
| `arena runners` | N | arena, one candidate per seat |
| `arena cross-judge pool` | N | arena, pick one seat whose model family differs from the parent's |
| `swarm workers` | 1 | swarm, default model for every worker |
| `skill tests` | 1 | pstack-author-skill fresh-child test and description eval |
| `architect runners` | N | architect, one runner per seat |
| `interrogate reviewers` | N | interrogate, one reviewer per seat |
| `verifiers` | N | swarm-verify, autopilot, shipping, orchestrate verification |
| `review backups` | N | `roles.py backup`, when every paid reviewer backup is out |

### Built-in defaults

`roles.py show` owns this mapping. A skill must not rebuild it.

Code roles (`feature, refactoring`, `bug-fix`, `perf-issue`, `hillclimb`, `swarm workers`, `reflect tooling`) use `grok-4.7` at xhigh. Judgment roles (`judgment and prose`, `hardest tasks`, `how explainer`, `why synthesizer`, `reflect judgment, divergent, synthesizer`) use `claude-opus-5-5` at xhigh. `arena runners`, `arena cross-judge pool`, `architect runners`, and `interrogate reviewers` use those two seats in that order. Every seat follows [Excluded seats](#excluded-seats), so a `grok-4.7` seat on a provider whose model declares `fastMode` comes back with `"fastMode": false`.

`skill tests` uses `claude-haiku-5-5` at high. `how explorer` and `why investigators` use `claude-haiku-5-5` at medium, per [Claude Haiku 5.5](#claude-haiku-55).

`verifiers` starts with `"inherit"` when this thread's provider can run children, then adds one seat per other runnable provider (`canRunChildTask: true`), using that provider's first pickable model and skipping a family already seated. A thread on an excluded model gets no `"inherit"` seat, and its own provider joins with its first pickable model instead. With only one runnable provider, `verifiers` is three `"inherit"` seats, or three copies of the one runnable provider's first pickable model when this thread cannot be inherited, and the report must say the models did not differ. The other panel roles do not use that three-seat rule.

A model family is the leading word of the model ID. `claude-opus-5-5` is `claude`, `gpt-6.1-sol` is `gpt`, and `grok-4.7` is `grok`. The normalizer in [Excluded seats](#excluded-seats) runs first, so `us.anthropic.claude-sonnet-5-5-v1:0` is `claude`. Diversity rules compare families, never providers, because one provider can serve another's models.

A preferred seat that matches this thread stays an explicit target. It does not become `"inherit"`.

When the preferred model is missing, the seat stays and a numbered note names the role, the seat number, the wanted model, and the replacement. The replacement is the first pickable runnable model of that family, then this thread's model when its provider can run children and the model is pickable, then the first pickable runnable model in the catalog. No runnable provider is an error. The panel keeps every seat. When two seats land on the same model, the note says the panel lost a distinct model.

Without a catalog, a preferred role reports `"seats": "catalog-required"`. `skill tests` reports `"seats": "catalog-required"` like the other preferred roles. `verifiers` reports `"seats": "default-panel"`.

`review backups` has no built-in seats, so `show` reports `"seats": "unset"` until the user sets it. Once it is set, `show` needs a catalog and reports `"seats": "catalog-required"` without one. With a catalog it prints the seats `backup` keeps when no provider is out and no author is named, and a `dropped <provider>/<model>: <reason>` note for each other seat that [Excluded seats](#excluded-seats) does not skip first. When a seat is dropped, `validate` lists it and exits 1, and `write` refuses the config unless `--force` is passed.

Agreement between seats on the same model is weak evidence. It shows the prompt is stable, not that the finding is right. Weigh consensus only across seats on different models, and say which kind you have.

### Excluded seats

pstack never runs a fast Grok model or Claude Haiku 4.5 as a seat or a worker. A fast Grok seat is a grok-family model whose id carries a `fast` token, such as `grok-4.7-build-fast`, or a Grok seat with `fastMode` set to `true`. `grok-build` has no `fast` token. A Claude Haiku 4.5 seat has a model id such as `claude-haiku-4-5`, `claude-haiku-4-5-20251001`, `claude-haiku-4-5@20251001`, or `anthropic/claude-haiku-4.5`. One normalizer maps that id to its canonical form before the Haiku 4.5 exclusion and before the Haiku 5.5 identity check. It removes a provider path prefix such as `amazon-bedrock/` and folds case. It strips one leading Bedrock prefix, `anthropic.`, `us.anthropic.`, `eu.anthropic.`, `apac.anthropic.`, or `global.anthropic.`. It treats dots and underscores as hyphens. It strips a Vertex `@YYYYMMDD` suffix and a trailing `-YYYYMMDD` suffix. Haiku 4.5 then matches `claude-haiku-4-5` at a hyphen boundary. Haiku 5.5 matches the canonical id `claude-haiku-5-5`. A pickable model is one that is not excluded. Every automatic pick in this file takes a pickable model.

- No picker chooses an excluded id.
- Every seat on a Grok model that declares a boolean `fastMode` option comes back with `"fastMode": false`. No mode and no budget sets it to `true`. pstack never adds `fastMode` to a model of another family.
- An `inherit` seat on an excluded id becomes that provider's first pickable model, with the note `inherit replaced by <provider>/<model>`. When that provider cannot run children or has no pickable model, `show` refuses the role.
- An `inherit` seat on a Grok model that declares `fastMode` becomes an explicit seat on that model with `"fastMode": false`, and the info `inherit made explicit as <provider>/<model> so fastMode stays false`. When that provider cannot run children, `fastMode` cannot be pinned, so `show` refuses the role.
- `show` skips a configured excluded seat with the note `skipped configured seat <provider>/<model>`. When no configured seat is left, the role uses its built-in default. `validate` lists each one and exits 1. `write` refuses it with `refusing to write, even with --force`. With a catalog, a `review backups` role with no configured seat left reports `"seats": []`.
- `verifiers` gets no `inherit` seat for an excluded parent, with the note `skipped inherit of <provider>/<model>`, per [Built-in defaults](#built-in-defaults).
- Without a catalog, a role whose seats include `inherit`, and the `verifiers` default panel, report `"seats": "catalog-required"` when `--parent` names an excluded id. Call `orchestrator_capabilities` and rerun `show` with `--catalog`.

### Budget

The config may carry `"budget"`: `default`, `small`, `medium`, `large`, or `unlimited`. It caps the reasoning option of every seat that has one (`effort`, `reasoningEffort`, `reasoning_effort`, or `reasoning`) at `medium`, `high`, `xhigh`, or the highest level at or below `max`, or the closest lower value the model offers. A seat that names its own reasoning level keeps it when it is at or below the budget level, and is lowered to the budget level otherwise. `default` leaves options alone. The built-in Opus and Grok seats name xhigh, so `default` leaves that level in place. The ladder stops at max. `unlimited` raises those two seats to the model's highest level at or below max. The default Opus seat moves from xhigh to max. Grok stays at xhigh, the top of its ladder. `unlimited` does not raise the Claude Haiku 5.5 seats, per [Claude Haiku 5.5](#claude-haiku-55). `unlimited` lowers a configured `ultra` seat to max when the model offers a level at or below max. `default` keeps a configured `ultra` seat. When every offered level is above the cap, the seat gets the lowest level. Verifiers use those same levels. `ultracode` and `ultrathink` are never chosen by a budget. Under any budget other than `default`, an `inherit` seat becomes an explicit target on this thread's provider and model with the budgeted option, because an omitted `target` would pass the parent's reasoning level through. `roles.py show` reports the budgeted seats.

### Fallback

A configured seat whose provider is not runnable, or whose model is not in the catalog, falls back on its own. This path is separate from the built-in order above. A configured excluded seat never takes this path. A `review backups` seat never takes it either. `show` drops that seat with a note. [Excluded seats](#excluded-seats) says how each command handles it.

1. Use the same provider's first pickable model. When it has none, `show` refuses the seat.
2. If the provider is not runnable, use `"inherit"`, settled per [Excluded seats](#excluded-seats).
3. Say which seat changed and why. Never silently drop a seat, because the seat count is the panel size.

Built-in preferred seats use the numbered notes from [Built-in defaults](#built-in-defaults). Those notes name each replacement, and the panel size never shrinks.

`roles.py validate --catalog <file>` checks a config against a saved catalog file. Use the file path there. The quoted heredoc above is for `show` when the catalog is still a tool result.

### Claude Haiku 5.5

`skill tests`, `how explorer`, and `why investigators` use Claude Haiku 5.5 by default. `skill tests` runs at high effort. `how explorer` and `why investigators` run at medium. Anthropic positions Haiku 5.5 for high-volume, latency-sensitive work such as classification, routing, extraction, and sub-agent tasks, and for reading-heavy workers that search, read, and extract with little hard reasoning. A worker that needs more judgment takes Sonnet, and hard work takes Opus. Effort defaults to medium, and high fits work where instruction following matters. `unlimited` does not raise these seats.

Anthropic documents two weak spots that these paragraphs answer. At low effort, Haiku 5.5 stops early in long agent prompts. At low or medium effort, it skips verification on coding work. `roles.py show` adds both paragraphs as `haikuBrief` to every role entry with a seat that runs Haiku 5.5, including `inherit` on a Haiku 5.5 thread. Paste them unchanged, in order, at the end of the child's brief, per [Delegation](#delegation) step 4.

Keep working until everything the user asked for is done, and only stop to ask when you can't go on without the user or before a risky step. When the work the user asked for is done and checked, stop and report. Don't add new features, docs, or refactors that weren't asked for. If you think one would help, mention it at the end instead of doing it.

When you change code that can be run, built, or type-checked, run a real check that exercises the change before reporting it done: the project's tests, type-checker, or build, or the changed command itself. A syntax-only check, or a check command that failed to start, does not count; if all that is missing is the project's declared dependencies, install them with its own package manager and lockfile (e.g. npm install, pip install -r requirements.txt), never via sudo or the system package manager, unless told not to. Only if no real check can run here, say which one you did not run and why instead of reporting the change as done.

A child launches seats when it passes a `target` to `delegate_task` or a `modelSelection` to `t3_thread_launch`. A skill-test child that launches seats resolves with `roles.py show --role "skill tests" --launches-seats`. Pass exactly one `--role "skill tests"`, a catalog, and `--parent`.

The pool first uses the providers named by explicit configured seats in single-seat roles, never cursor. If no such provider remains, it uses every runnable provider that serves a pickable model of a built-in default family, `claude` or `grok`, plus this thread's provider. It removes cursor from that pool too. Cursor's harness sends `target.options` as a JSON string, which T3 refuses. An empty pool refuses with `cannot launch seats`.

A configured `skill tests` seat on another provider uses the configured-seat resolution rules in [Fallback](#fallback). The pool does not limit that seat. A configured `skill tests` seat on cursor is ignored in favor of the built-in default. Ignoring cursor adds no note. A seat that resolves to cursor is refused with `cannot launch seats`, including `inherit` on a cursor thread.

## Modes

pstack-t3 runs each piece of work in `full` or `light` mode. Full mode runs every step as each skill says. Light mode keeps every check that decides whether code lands and cuts the fan-out around it. A skill or playbook that spawns links here. Its light behavior is the row below that names it, and its full behavior is its own text.

### Resolve and carry the mode

`roles.py mode` and `roles.py show` resolve one effective mode. The highest level present wins. The order is the brief, then the session, then the coordinator, then the project file `.pstack/t3-roles.json`, then the user file `roles.json`, then `full`.

- A brief's `Mode:` line is the frozen decision. A child copies that line's bare value into `--brief-mode` on every `roles.py mode` and `roles.py show` call it makes, and passes no other mode flag. It never resolves the mode again.
- The user's words set the session. `$poteto-mode light`, "light mode", or "use light mode" in a request sets this thread to light. "full mode" sets it back. A light session passes `--session-mode light` on every `roles.py` call that has no brief value, except the explicit reflect below.
- With neither, pass no mode flag. The roles files decide, and a missing key is `full`.
- A user's explicit reflect passes `--session-mode full` on every `roles.py show` call it makes, whatever the session or the roles files say. A call with no mode flag would fall through to a roles file that stores light. The session stays light after it.

Every brief whose child resolves seats or spawns carries the mode. Get the lines from `roles.py mode`, never from memory.

```bash
python3 <pstack-runtime>/scripts/roles.py mode --cwd "$PWD" [--playbook <name> --attempt <kind>] [--brief-mode <value> | --session-mode light]
```

- A code delegate's brief passes `--playbook <name> --attempt <kind>`. `<kind>` is `first` for new work, `fix` after a send-back, and `bounce` after a queue bounce. Paste the printed lines unchanged under the persona body. They start with the `Playbook:` line, so write no `Playbook:` line of your own. See [Delegation](#delegation) step 4.
- An owner, sub-coordinator, unit worker, visual-parity owner, or landing writer is not a code delegate. Run the command without `--playbook` and `--attempt`, and paste its `Mode:` and `Mode source:` lines into the brief or the `message`. Right after them, paste the seat rule below unchanged. A launched thread has no parent to ask, and a `Mode source: session` line reads like a session of its own without it.

  ```text
  Seat rule. Copy the Mode value above into --brief-mode on every roles.py mode and roles.py show call you make, and pass no other mode flag. Never pass --session-mode. Mode source names where your launcher's decision came from. It does not make this thread a session.
  ```
- A read-only leaf, such as a `how` explainer or a reviewer, gets no `Mode:` line. It resolves no seat.
- A light session with no brief runs the same command with `--playbook <name> --attempt first` for its own playbook. Its `Waived by mode:` line names the steps this thread skips.

Under light with budget `default`, `roles.py show` resolves seats as budget `small`, which caps reasoning at `medium`. An explicit budget wins. No mode sets `fastMode` to `true`. A Grok seat that declares it gets `false`, per [Excluded seats](#excluded-seats). Pass the live catalog and `--parent` on every light `show` call, per [Roles](#roles), so an `inherit` seat gets the cap.

Escalation only moves work toward `full`. `roles.py mode` prints `Mode: full` and `Mode source: escalated: <reason>` when a lease covers a pattern in the project's `"escalate"` list, at the second send-back, or when `--escalated` carries a recorded reason. A light thread that finds its design contested does not run `interrogate`. A thread whose brief has a `Mode:` line stops at a verifiable point and reports `Contested: <reason>` under its status. A thread whose mode came from the session or the roles files switches that work to full, announces the escalation, and runs the step full mode prescribes, such as `interrogate`. Nothing moves work from full to light mid-flight.

### Light behavior

In light mode, run the row for the spawn you are about to make. A step its row does not change runs as the skill says. A smaller fan-out in a row is how that step runs, not a waiver. Waived steps come only from the brief's `Waived by mode:` line, which `roles.py mode` prints from `LIGHT_WAIVERS`. Never add a waiver of your own. No light fan-out wave has more than 3 children in flight. A wave with more slices batches them into 3 briefs and keeps every slice covered.

| Spawn | Light behavior |
| --- | --- |
| `how` | Take the simple path for every question. Spawn one `how explainer`. Spawn no `how explorer`. |
| `why` | Spawn the source-control investigator only. Spawn no synthesizer. The parent writes the synthesis under `why`'s evidence and confidence rules. |
| `architect` grounding | Reuse the `how` output the calling playbook already holds. Run `how` once only when there is none. |
| `architect` runners | Spawn one runner on the first `architect runners` seat and ask it for two structurally distinct sketches. Screen both against `references/design-red-flags.md`. The parent picks one. |
| Arena cross-judge | Spawn no judge. The parent picks. The [gate review](#gate-review) reads the chosen design. |
| Arena candidates | Hand code to the single code delegate. Eval keeps arena and its judge, because comparing candidates is its whole purpose. |
| Code delegate | Keep it, with the persona, the `roles.py mode` lines, and `roles.py check-brief`. Hillclimb runs one live hypothesis at a time. |
| Comment Sicko | Spawn no Comment Sicko child. The worker applies `agents/comment-sicko.md` to its own diff. The [gate review](#gate-review) checks the same rules. |
| Comment Sicko follow-ups | Spawn no follow-up `how`, `why`, rerun, or `architect`. A finding that needs one goes into the gate verdict as a send-back. The contract in [Gate review](#gate-review) step 2 tells the reviewer the same. |
| `interrogate` | No playbook runs it. A contested design escalates per [Resolve and carry the mode](#resolve-and-carry-the-mode). A child that opens a PR runs the [gate review](#gate-review) in its place. |
| Fresh-child skill tests | Run one executing test per changed spawn or coordination behavior, on the `skill tests` seat. A leaf test may forbid spawning only when the behavior needs no delegation. Skip the second-provider test. |
| Description eval | Run it only when the change edits a `description`. |
| `swarm` | Spawn at most 3 workers. A respawn replaces a worker and does not raise the count. |
| Trail reviewer | When a gate review runs at the hand-back head SHA, it reads the trail and no trail reviewer runs. A code delegate never launches one, because its parent's gate reads the trail. With no gate at that head, the trail reviewer runs and is the gate, under [Gate review](#gate-review) steps 1 to 4. |
| `reflect` | A scheduled reflect, such as a coordinator's weekly service, does not run. A user's explicit reflect runs in full. Its `roles.py show` calls pass `--session-mode full`, so the light `medium` cap does not apply. |
| `recall` | Spawn at most 3 slice children. Run no `why` wave unless the user asks for one. |
| `automate-me` | Spawn one miner over the whole history window. Its brief lists every `threadId` that `t3_thread_list` returns in the window, across every page. The parent filters and samples none, and tells the miner to read each one. |
| Verification source wave | Spawn at most 3 source children, each reading a batch of feature files. |
| Multi-phase exploration | Spawn one read-only explorer. |
| Multi-phase verification | Write the plan's lane checklist as the playbook and `check-plan.mjs` require. At each code-ready head, launch the gates lane, one live lane per surface, and one audit lane on another model family. That audit lane is the gate review and runs [Gate review](#gate-review) steps 1 to 4. Each live lane's brief carries the boot recipe and every **Verify, live** lane box that drives its surface, and tells the lane to run and report each box. Launch no perf lane. The perf boxes stay in the plan and are not a merge gate. |
| Autopilot owner | One owner per PR. Each owner `message`, including a replacement's, carries the mode lines and the seat rule from [Resolve and carry the mode](#resolve-and-carry-the-mode). |
| Autopilot verification | Two lane children per round. The gates lane reruns the gates at that SHA and keeps the patch-id rule in `playbooks/shipping.md`. One audit lane on another model family is the gate review. It runs [Gate review](#gate-review) steps 1 to 4 at every new head SHA. |
| Orchestrate sub-coordinator, worker, and long-lived owner | Keep them. Each brief or `message` carries the mode lines and the seat rule from [Resolve and carry the mode](#resolve-and-carry-the-mode). |
| Orchestrate verifier | Keep it when verification is expensive. A cheap unit's merge still needs the gate review at its head, per [Gate review](#gate-review) steps 1 to 4. |
| Shipping verifier | One per PR. It is the gate review. It runs [Gate review](#gate-review) steps 1 to 4 with Shipping's live test as its own tasks, and it reuses a verdict only per [Gate review](#gate-review). |
| Visual parity owner | One owner per component, at most 3 in flight. Each `message` carries the mode lines and the seat rule from [Resolve and carry the mode](#resolve-and-carry-the-mode). |
| Worktree cleanup summarizer | Spawn none. The parent reads the last page of each long thread with `t3_thread_read` and `limit`. |
| Landing writer | One writer per unit. Its brief or `message` carries the mode lines and the seat rule from [Resolve and carry the mode](#resolve-and-carry-the-mode). |
| Autonomous run watcher | Keep it. |
| Setup smoke test | Keep one per provider. |

A send-back in light mode is a fix attempt with a fresh worker. Its brief carries the findings, the old head, and the `Attempt: fix` lines `roles.py mode` prints.

### Never cut

- Tests and the build. The worker runs the project's test command and build before every gate review, and the landing queue reruns them.
- The landing queue's checks.
- One review by another model family at every head SHA before merge, per [Gate review](#gate-review).
- A fix attempt's review reads the whole diff against its base, not only the change since the last review.
- Owner fences. Leases, `--owner` generations, worktrees, and the pass-at-head gate.
- A fresh worker for every send-back, per [Fresh children by default](#fresh-children-by-default).
- The code delegate, with the persona, the `roles.py mode` lines, and `roles.py check-brief`.
- One executing fresh-child test per changed spawn or coordination behavior.

### Gate review

Light mode removes the panels that give full mode its model diversity. The gate review puts one read by another model family back before merge. Full mode keeps each playbook's own review steps.

Every child that acts as the gate review runs steps 1 to 4. That includes the audit lane, the Shipping verifier, a cheap Orchestrate unit's gate, and a trail reviewer that runs with no gate at its head. Its step 2 brief adds that child's own verification tasks below the contract. Launch no second child for the same gate.

1. **Seat.** Resolve `verifiers` per [Roles](#roles) with this work's mode flag. Take the first seat whose model family differs from the author's. The author is the code delegate's `providerInstanceId/model`, or this thread's when it wrote the code. When several models wrote the diff, the verifier's family differs from all of them. When no runnable seat qualifies, the verdict is `blocked`.
2. **Brief.** A read-only brief. Give the base ref and the full head SHA, and ask for a read of `git diff <base>...<head>`, the whole diff. Paste the body of `agents/comment-sicko.md` unchanged and ask for its findings on the diff. Right after that body, paste the gate contract below unchanged. Add the child's own verification tasks after the contract. Name the chosen design's path when the light architect step picked one of two sketches. Name the decision log path and the run's `threadId` when the run kept a trail per `show-me-your-work`, and ask the reviewer to run that skill's audit checks itself with `t3_thread_read`. Flag weak evidence, skipped or unproven verification, misleading readiness, and a shell success that hides a failed check.

   ```text
   Gate review contract. These rules override the persona above and the tasks below where they differ.
   Do not edit files, commit, or push. Do not post on the PR. Return your report to the parent.
   Launch no child task, thread, or subagent. Do not run the how, why, architect, or interrogate skill. Do not launch show-me-your-work's trail reviewer.
   Read the whole diff and the nearby code yourself. You may run git log -L and git blame. Run the named verification commands yourself.
   When a claim or finding needs investigation beyond those reads, return send-back. Name the file, the line, the claim, and the question the fix must answer.
   Report each comment the persona would delete as a send-back finding with its path and line. Make no edit.
   End with pass, send-back, or blocked, the full head SHA, the author, and the verifier.
   ```
3. **Verdict.** `pass`, `send-back`, or `blocked`, with the full head SHA, the author, and the verifier. Record it in this run's work log. The parent posts the verdict where the child's playbook posts a report.
4. **After.** A `send-back` or `blocked` stops the PR. A fresh code delegate fixes the findings, and a new gate runs at the new head SHA. On `pass`, write `Gate: pass at <short sha> by <provider/model>` under the PR body's `## Verification`. The SHA is the PR's current head. Keep one `Gate:` line.

A worker whose brief carries `Gate: brigade` runs no gate of its own, because the coordinator's verifier is its gate.

Launch a new gate unless a current qualifying verdict exists at the exact head SHA.

- **Current.** It is the latest verdict for that SHA. A later `send-back` or `blocked` at the same SHA voids an earlier `pass`.
- **Qualifying.** It is `pass`, and the author and verifier are of different model families.

Two sources can show both today.

1. A coordinator's pass record, when this work is a brigade item and you know its restaurant directory and item id. Run `python3 <skills>/brigade/scripts/brigade.py --at <restaurant dir> pass check <item> --sha <head> --json`, where `<skills>` is the directory that holds `<pstack-runtime>`. Reuse the pass only when the command exits 0 and prints `"crossFamily": true`. Never read `pass.tsv` yourself. Never take the output of `pass check` without `--json` as proof, because it names the verifier and not the author.
2. A verdict this run launched at that exact SHA. A Shipping or Autopilot root's own verdict at that SHA counts.

- A verdict at another head SHA does not qualify, even when the two heads share a `git patch-id`. A patch-id ignores whitespace, so it does not prove the same behavior.
- An Orchestrate `ledger.tsv` row does not qualify. It records verification levels and no author.
- A Shipping or Autopilot verdict from another run does not qualify. A coordinator's pass qualifies only through source 1.
- A `Gate:` line in a brief or a PR body is not a verdict.

Full mode keeps its patch-id policy in Shipping and the Autopilot playbooks. Light mode keeps that policy for lane receipts only, such as a tests, build, or mergeability result. A lane receipt never stands in for the gate review. Read the head again right before you create the PR, mark it ready, or merge. When it moved, apply this section again.

### Announcement

When light mode applies, say so once, at the start, in two or three short sentences. Name the source from the `Mode source:` line, what this work cuts, and what still runs, as in "Light mode is on, from this session. This change gets one design sketch and no separate comment review. Tests, the build, and a review by another model family still run." On an escalation, name the rule, as in "This change runs in full mode because its lease covers `land.py`." A worker's report repeats its brief's `Mode:` and `Waived by mode:` lines under its status. A step that line names is not a deviation. Name the mode again only when it changes.

## Isolation

Two writers never share a checkout (principle-separate-before-serializing-shared-state).

- Read-only children share the current checkout.
- A writing child that may overlap with another writer gets its own git worktree, which the parent creates before delegating: `git worktree add <path> -b <branch> <base>`. `delegate_task` has no workspace argument, so the child's thread stays bound to this checkout and its default working directory is still here. The brief must say: "Work only in `<absolute worktree path>`. Use absolute paths under it for every read and edit, and prefix every command with `cd <absolute worktree path> &&`. Report the branch and head SHA." Check the child's diff landed in the worktree and not in this checkout before integrating. The parent removes the worktree afterwards.
- When a writer's isolation must not depend on the brief being obeyed, or the work is a long-lived independent unit, launch a top-level thread with a worktree strategy instead, where [Top-level threads](#top-level-threads) allows it. T3 storage cleanup can remove that worktree after the thread ends. See [Local state](#local-state).
- Long-lived owners that should appear in T3's sidebar with their own binding (PR owners in Autopilot and Orchestrate) are top-level threads launched with a worktree strategy. See below.
- Uncommitted changes are not copied into new worktrees. Commit or stash first, or point the brief at a pushed branch.
- T3 runs the first effective project action with `runOnSettle: true` each time a thread settles in its own worktree, including auto-settlement. A thread in the main checkout skips it. The effective list is the project's override, else the environment defaults. Actions in a repository `t3.json` count only once imported into project settings, and either list can replace them. `t3_project_read` returns the project's saved `scripts`, which can differ from the effective list. Before you settle a worktree thread, read T3's `settings.json` (`~/.t3/userdata/settings.json` by default). Take `projectSettingsOverrides.<projectId>.defaultProjectScripts` when present, else `defaultProjectScripts`, and name its first `runOnSettle: true` action or none. When `projectSettingsFolded` is not `true`, older saved lists still count, so treat the action as unknown. The action can run beside another terminal command. Its terminal closes on success and stays open on failure. It is a cleanup hook, not a wake, so never schedule a tick to watch for it.

## Local command capacity

Children, launched threads, and this thread run on this machine, so their builds and tests share its cores. Run each local build, test suite, and verifier rerun through `python3 <skills>/landing/scripts/land.py slot -- <command>`, where `<skills>` is the directory that holds `<pstack-runtime>`. Run each benchmark or timing measurement through `python3 <skills>/landing/scripts/land.py slot --exclusive -- <command>`. It must be the outermost slot. The slot count, its config file, and the landing queue's reserved slot are in the landing skill's [Capacity](../landing/SKILL.md#capacity) section. A brief links that section and does not copy them.

- A slot wraps one command and ends when that command exits. Never hold a slot across a model turn, a `t3_thread_wait`, a `task_status` check, a `watch_pull_request` wait, or any other wait on children. Start dev servers with the preview tools, not in a slot.
- Slots limit heavy commands, not agents. Do not cap owners, children, or launched threads at the slot count.

## Top-level threads

Create top-level threads only when the user asked for separate threads or invoked a playbook or skill that names them (Orchestrate, Autopilot-full, Autopilot-stack, brigade). Invoking those is that request. Everything else uses child tasks.

```json
{
  "title": "PR owner: <slug>",
  "workspaceStrategy": {"type": "worktree", "baseRef": "main", "branch": "pstack/<slug>", "startFromOrigin": false},
  "message": "<brief>",
  "modelSelection": {"instanceId": "claudeAgent", "model": "claude-opus-5-5", "options": {"effort": "xhigh"}}
}
```

- `modelSelection` is the seat with `providerInstanceId` renamed to `instanceId`, `model` copied, and `options` copied unchanged as the same object, including a boolean such as `{"fastMode": false}`. Omit `modelSelection` for an `inherit` seat.
- Confirm a launched thread per [Delegation](#delegation) step 3.
- For a stack, `baseRef` is the parent branch and `startFromOrigin` is false.
- Omitted `workspaceStrategy` means the project root, not your worktree.
- `t3_thread_launch` requires a full-access or default caller. In `approval-required` or `auto-accept-edits` it fails. Then fall back to child tasks isolated per [Isolation](#isolation), and tell the user that owners are children rather than threads.
- `t3_thread_launch` has no retry key. Retain the `threadId`. After an error or lost response, check `t3_thread_list` before retrying. Report it to the user as a thread link per [History](#history).
- Follow a thread with `t3_thread_wait` and read it with `t3_thread_read` (use `afterPosition` to read only what is new). Send follow-ups with `t3_thread_send`, interrupt with `t3_thread_interrupt`.
- A thread launched with `t3_thread_launch` has no parent. Its finished turn does not wake the launcher. A launcher that needs a report names the message the launched thread sends with `t3_thread_send`.
- Autopilot-full, Autopilot-stack, and Orchestrate owners send their report lines to the root or coordinator with `t3_thread_send` and `mode: "auto"`. `auto` starts an idle recipient, steers a fully active turn, and queues behind a turn that cannot accept steering yet. It does not merge reports into one turn. The recipient handles every report, steered or queued, and runs the playbook's head-specific checks on the head each report names. Arrival order never makes a head current. Brigade's event lines to an executive admin stay on `mode: "queue"`, as [Reporting to an executive admin](../brigade/SKILL.md#reporting-to-an-executive-admin) states.
- A correction you queued earlier to an active owner or coordinator can sit behind a long turn. To deliver it into the run, call `t3_queue_list` on the recipient and find the `queuedRunId` of that exact message. Read the recipient's `activeRunId` with `t3_thread_read`. Call `t3_queue_promote_to_steer` with that `queuedRunId`, the `activeRunId` as `targetRunId`, and the recipient's `threadId`. Its `sequence` result means T3 accepted the call, not that the run received the message. Read the recipient with `t3_thread_read`, `view: "activity"`, and `afterPosition`, and find the correction's text in that run. Until that read shows it, the delivery is unresolved. A `cancelled` queued run alone proves nothing. When the active run changed or T3 refused the promotion, read `t3_queue_list` and the recipient again before you act, and never resend a correction that may already be delivered. Never promote brigade's event lines to an executive admin, a digest message, or a message that needs a turn of its own. Send a new correction with `mode: "steer"` or `mode: "auto"` instead of queuing it.
- Change an existing launched thread's model with `t3_thread_configure` only when a playbook step already calls for that owner to run on another model, such as Orchestrate's tool-error retry. Never call it because an owner keeps failing a gate. Resolve the seat per [Roles](#roles) with `roles.py show`. `t3_thread_configure` requires a concrete `modelSelection`, so always pass one, even for an `inherit` seat. Build it from the resolved seat with `providerInstanceId` renamed to `instanceId`, `model` copied, and `options` copied unchanged. When the resolved seat is `inherit`, use this thread's own provider and model, `inheritedProviderInstanceId` and `inheritedModel` from `orchestrator_capabilities`, as the concrete seat when it passes [Excluded seats](#excluded-seats). When it fails that check, do not configure the thread, and report that no replacement seat could be selected. Call it when `t3_thread_read` shows no `activeRunId`, or after `t3_thread_interrupt` and `t3_thread_wait` end the run. Before the thread's next message, read `t3_thread_configuration` and compare `instanceId`, `model`, and every option per [Delegation](#delegation) step 3. On a refusal or a mismatch, send nothing to the thread and report the tool's error text. The call does not change the thread's permission modes, and it keeps the thread's retry count, scope, standing orders, and gates. The thread keeps its history, so it never counts as a fresh worker or a fresh reviewer. Never configure a verifier or reviewer thread. A failed child task gets a fresh child per [Failure handling](#failure-handling). A send-back and a usage-limit relaunch get the fresh worker their playbook or `roles.py backup` names. None of them uses `t3_thread_configure`.
- `create_threads` makes up to 20 threads sharing this checkout. Use it only for read-only fan-out the user wants visible as threads.

### Forks

`t3_thread_fork` starts a new top-level thread from another thread's context. `t3_thread_merge_back` moves context between related threads in one project. Use them only for a separate thread this section allows. Child work stays on `delegate_task` per [Delegation](#delegation) and [Fresh children by default](#fresh-children-by-default). A fork never stands in for a child task, an Orchestrate sub-coordinator, or a fresh review round, and `task_status` does not apply to it.

- Fork only a read-only planner or investigation whose source context is the part it needs. Pass `sourcePoint` as `{"type": "latest_stable"}`, `{"type": "run", "runId": "<id>"}`, or `{"type": "checkpoint", "checkpointId": "<id>"}`. Keep the returned `targetThreadId`.
- The fork inherits the source's configuration. Read it with `t3_thread_configuration` before the fork's first message, and check it against [Excluded seats](#excluded-seats) and the user's roles. Inheritance is not an exception. When the inherited seat fails that check, send the fork nothing and report it.
- Read the fork with `t3_thread_read` for its `worktreePath`, `branch`, and `activeRunId` before you send anything. Treat a checkout it shares with another thread as read-only. Writers stay isolated per [Isolation](#isolation).
- Send its scope with `t3_thread_send`. The message names the slice, says "do not edit files, commit, or push", and names the report line and the thread ID that line goes to with `t3_thread_send`. Follow the fork as a launched thread with `t3_thread_wait` and `t3_thread_read`.
- A one-line report stays the default. Call `t3_thread_merge_back` only when the user authorized it and the target needs the fork's reasoning, not only its result. Pass `targetThreadId` and `sourcePoint`, and `sourceThreadId` when the source is not this thread. Read `t3_thread_transfers` and the target's later activity with `t3_thread_read` to see what the target received. A transfer moves context, not code, and it does not make a review independent.

## Scheduling

`schedule_task` creates recurring work in T3's scheduler. It runs even when no turn is active, so it replaces `/loop`, Cursor automations, and hourly ticks.

```json
{"title": "autopilot tick", "prompt": "<self-contained tick prompt>", "schedule": {"type": "interval", "everyMs": 3600000}, "clientRequestId": "<skill>-<slug>-tick"}
```

- Pass `schedule` as an object. `everyMs` is at least 60000. Wall-clock runs use `{"type": "fixed_time", "timeOfDay": "09:00", "weekdays": [1,2,3,4,5]}`.
- Runs post into this thread by default. Set `bindToCurrentThread: false` only when each run should start a fresh thread.
- The tick prompt must stand alone. Point it at the work log or store so a run can rebuild state from disk.
- Report the returned cadence and `nextRunAt`. Delete the schedule with `delete_scheduled_task` when the done predicate holds. List with `list_scheduled_tasks`.
- Pause a schedule with `update_scheduled_task` and `enabled: false`. Resume by setting it back to true.
- A finite program pauses a schedule that can only repeat an unanswered user decision. A finite program has a done predicate, as in Autopilot-full, Autopilot-stack, Orchestrate, and Autonomous run. The rule covers an audit or progress schedule when no item has runnable work and its next run can only raise the same user decision again.
- Write the decision and that schedule's ID to the work log or store the tick prompt names. Raise the decision once. Then call `update_scheduled_task` with that ID and `enabled: false`, and end the turn.
- On an answer that permits work, call `update_scheduled_task` with the same ID and `enabled: true`. On an answer that keeps the work parked, record the answer and leave the schedule paused. When the done predicate holds, delete the schedule with `delete_scheduled_task`. After a T3 restart, find the paused schedule with `list_scheduled_tasks` and the recorded ID.
- A tick queued before the pause can still run after it. It reads the record, does not raise the decision again, and does not re-enable the schedule.
- Never pause a schedule that renews a lease, drains queued work, consumes standing intake, or notices a merge. A required merge heartbeat and a fallback heartbeat beside `watch_pull_request` keep running. This rule never pauses a brigade schedule. Brigade holds an item on a decision and keeps its liveness schedule renewing the lease.
- Do not schedule a tick to wait for a child task. Child completions wake this thread, and [Delegation](#delegation) step 5 bounds the wait for a child that never completes.
- Do not schedule a tick to wait on a pull request's checks, reviews, or conflicts. That wait is [Pull request watching](#pull-request-watching). Keep `schedule_task` for a cadence with no PR event. Beside a watch, a fallback heartbeat uses `everyMs` of at least `3600000`. A required heartbeat whose job is to notice a merge may use `900000`, as that section states.
- To run an enabled `interval` schedule's work now, call `run_scheduled_task_now` with its ID as `taskId`. Take that ID from the work log or from `scheduledTaskId` in `list_scheduled_tasks`. Call it only when the work its next run does is ready and neither this turn nor a dispatched run is doing it. No event calls it by rule, a merge or an answer included. Each call is a new manual run. Before you retry a lost or failed response, read `list_scheduled_tasks` and the bound thread with `t3_thread_read`. The result means T3 dispatched the run, not that its turn finished. Follow a returned `threadId` with `t3_thread_read` when the result matters. Report the returned `nextRunAt` as T3 returned it. Never run a paused schedule before the answer permits work. Never run one to wait on a child, to wait on a pull request's checks, reviews, or conflicts, or to repeat a `watch_pull_request` wake. It requires a full-access or default caller. Under another mode, leave the work to the next scheduled run, or do it in this turn only when this thread owns that work and its mode allows the edits.

## Local state

Private working state that must survive the session but never be committed lives under `${XDG_STATE_HOME:-~/.local/state}/pstack-t3/`. Orchestrate stores go in `orchestrate/<project-slug>/`, private plans in `docs/<project-slug>/`. Children, launched threads, and scheduled runs reach it by the same absolute path from any worktree. Pass that path explicitly in every brief and tick prompt.

Resume notes from Pause safely go to `.pstack/resume/<slug>.md` in the repository, untracked (add `.pstack/` to `.git/info/exclude`), and are also posted as the thread's final message. Rely on the final message, because storage cleanup can delete the file with its worktree.

After a T3 restart, assume a child is gone unless `task_status` shows `working` or `waiting_for_children`. A task in `result_available` finished, so read its `summary` with `task_status` before you respawn its slice. Pushed branches, launched threads, thread history, and schedules persist. A T3-managed worktree persists unless the project enables storage cleanup. Storage cleanup removes a worktree that its rules select. It acts after the thread completes, is interrupted, is cancelled, or is rolled back. It also acts after the thread's PR merges into the default branch by squash or rebase at the worktree's head SHA. Depending on the user's cleanup settings, removal takes ignored files with the worktree, such as `.env`, build output, and `.pstack/`. It can take untracked files too. Commit and push the work itself, the tracked source changes, so it outlives the worktree. Never commit an ignored or private file to keep it. Keep private files in the state directory above. The branch and thread survive, and a new turn on that thread recreates the checkout. Resume through the thread's binding with `t3_thread_read`, and check that `worktreePath` exists before you use a saved path. Reattach through `t3_thread_list` and `list_scheduled_tasks`.

## Verification surfaces

- Web or Electron UI: `preview_open` the dev server URL, then `preview_snapshot`, `preview_click`, `preview_type`, `preview_press`, `preview_wait_for`, `preview_evaluate`. Use `preview_hover` to reveal a menu or tooltip, `preview_drag` to drop one element on another, `preview_select` to choose an option in a native select, `preview_upload` to give the page files, and `preview_dialog` to accept or dismiss a browser dialog. Record proof with `preview_recording_start` and `preview_recording_stop`. Check `preview_status` first. A call can fail because no preview host is available. Call `preview_status` again. Call `preview_open` if it lists no tab. Report a failure that persists. Never count that check as verified. Close each preview you opened with `t3_preview_close` and its `tabId`.
- Preview tabs. Pass the `tabId` that `preview_open` returns on every later preview call. Without it, T3 chooses the tab for you, which can be one you did not mean. The one exception is a new tab, which takes no `tabId` (see Clean state). Children that run in parallel on one provider session each open their own tab with `reuseExistingTab: false`. Act only on tabs you opened. Never act on a tab whose `owner` in `preview_status` is `human`, and treat another session's tab as read-only.
- Preview images. Pass `includeImage` explicitly on every `preview_snapshot`, because its default differs between builds. Pass `includeImage: true` when you need to see the page. When the result holds no image, or you need a PNG file, pass `save: true` and open the file at the `screenshotPath` it returns.
- Clean state. Do not assume a tab is logged out or logged in. Check. For a logged-out or first-run check, call `preview_open` with `reuseExistingTab: false`, no `tabId`, and an `incognito` `profileId` when `preview_status` lists one. Read the page with `preview_snapshot` and confirm it shows the state you need before you rely on it. Never clear storage in a profile a human uses.
- Devices and simulators: `device_list`, `device_open`, `device_screenshot`, `device_close`.
- CLIs and TUIs: run them in the terminal and assert on output.
- A project `verify-*` skill beats all of these when one exists.

## Visual reports

A page is for a reply that is already due. When the playbook that runs this thread sends a reply, and a table of units, a timeline, a frontier, or a chart would carry it better than prose, publish that part as a page. A short status with no table stays text.

1. Write one self-contained HTML document. Every number and link on it comes from the store or the tables the text report would read.
2. Call `html_preview` with it. Fix every console error and every clipped or overlapping element. When the page holds a wide table, preview it again with `width: 390`.
3. Call `html_render` with the document, a `title`, and the preview's `contentHeight` as `height`, raised to 80 or capped at 2000. A capped frame scrolls the rest.
4. Write the reply after the render. It does not announce the page and adds only what the page does not show. Every decision that waits on the user, every PR link, and the store and report paths stay in the reply text, so a capped frame never hides them.

Leave `html`, `body`, and the outermost element with no background color, and style the page with the theme variables `html_render` describes. When either tool is missing or `html_render` fails, send the same facts as text.

A rendered page is a reply the user reads, even with no reply text. Render none on a wake that sends no reply. Brigade at `digest` renders no page, so its replies stay in the plain form [Digest messages](../brigade/SKILL.md#digest-messages) sets. At every level, step 9 of brigade's [Run a service](../brigade/SKILL.md#run-a-service) decides which wakes reply before any page is drawn.

## History

- Find prior work: `t3_thread_search` with a topic, branch, or PR number. It covers the current project.
- Read it: `t3_thread_read` with `view: "messages"` for the conversation, `view: "activity"` for tool activity. Page with `afterPosition`. Recover long items with `itemId` and `textOffset`.
- A thread the user attached as context is readable even outside this project.
- Child tasks are threads too. A `childThreadId` from `delegate_task` is readable with `t3_thread_read`.
- `t3_thread_read` returns the thread's `worktreePath` and `branch`. `t3_thread_list` does not, so finding the threads bound to a worktree takes one read per thread. Threads from other projects are not visible.
- `t3_thread_list` and `t3_thread_read` report `snoozed` and `snoozedUntil`. Pass `snoozed: true` to `t3_thread_list` to find snoozed owners. `t3_thread_organize` with `action: "snooze"` requires `snoozedUntil`. A snoozed thread wakes early when it asks for something, fails, or completes. Snooze is a sidebar state. It is not a schedule, a completion, or a settle. Wait with `schedule_task` or `watch_pull_request`, never with `snoozedUntil`.
- Link a thread in a user-facing report as a Markdown link whose text is the thread's title and whose target is `t3-thread://v1/<threadId>`. Copy the `threadId` exactly as a tool returned it. Do not URL-encode it, decode its `%` escapes, or add an environment ID. T3 Code shows the thread's current title. List, read, and launch results carry no `link` field, so build the link from `threadId` or `childThreadId`.

## Pull requests

After you open a PR or start driving an existing one, call `link_pull_request` with its full URL. For a stack, link every layer. Linking attaches the PR to the calling thread. When a child opens a PR, it links it and the parent links it too. When a launched thread opens a PR, it links it and the launcher or coordinator links it too. Linking twice is safe. Before finishing PR work, call `list_thread_pull_requests` and link any missing PR. Report a link failure instead of claiming the PR is linked.

## Pull request watching

Call `watch_pull_request` after `link_pull_request`, when this thread is waiting on that PR's checks, reviews, or conflicts. Pass the PR URL, or the repository and number. T3 links the PR first if this thread has not linked it yet.

T3 checks the open PR every two minutes. It wakes this thread when a check fails, the required checks pass, someone else comments or reviews, or the branch starts to conflict with its base. Only comments posted after the call wake you, so handle the comments already on the PR, then end the turn.

One thread may hold several watches. Comments from the user's own account do not wake a watch, so a review left from that account needs another wake or the heartbeat. T3 documents both in [source control](https://github.com/pingdotgg/t3code/blob/main/docs/user/source-control.md).

A wake is news, not a merge decision. Read the PR and decide yourself before you merge.

A subagent cannot watch. The parent thread owns the PR. The child finishes and reports back. The thread that owns the PR calls `watch_pull_request`.

Call `unwatch_pull_request` when this thread stops driving the PR and hands that work back to the user. An interim status reply keeps the watch. The PR stays linked. While T3 watches, the thread stays in the user's Working list. Unwatching returns the thread to their inbox.

A merge ends the watch and does not wake the thread. A close ends the watch and does wake the thread. Watching also ends when the thread settles or is archived, when the user stops the thread, or when you call `unwatch_pull_request`. It also ends when T3 fails to read the PR 8 times in a row. A host rate limit only delays the next read. A watch ends after 10 wakes in a row that bring only comments, and that end posts a wake. Call `watch_pull_request` again after that wake when the loop is still running.

If the thread is settled, call `t3_thread_organize` with `action: "unsettle"` first. A settled thread's new watch ends on the next pass and posts no wake. A pinned thread does not auto-settle. A pinned coordinator runs that action only when someone settled the thread by hand. `t3_thread_organize` with `action: "settle"` and no `threadId` settles this thread when the turn completes, and returns `settlesWhenTurnEnds: true`. That return is an accepted request, not a settled thread. A failed or interrupted turn, or a queued message, leaves the thread active, and a T3 restart before the turn ends drops the request. Settle this thread only as the last call of a turn whose work is done. Never settle an owner whose PR watch or `schedule_task` loop is still needed, because settling ends the watch.

pstack's `scripts/watch-pr` poll, a foreground `--watch`, and an interval tick that waits for CI, a review, or a conflict all become this call. The forge commands that classify a verdict stay. Run them after a wake. They are not the wait.

`schedule_task` stays for a cadence that has no PR event, such as an hourly audit, a morning report, or a soak. Beside a watch, a fallback heartbeat uses `everyMs` of at least `3600000`. When the event you are waiting for is the merge itself, create a `schedule_task` heartbeat beside the watch. That heartbeat is required. A merge never wakes the thread, so the heartbeat is how you learn that the PR merged. The required heartbeat may use `everyMs` `900000`. Use `900000` while a landing entry is awaiting merge in human mode, while the PR is behind a merge queue, and for any other wait whose predicate is the merge. In merge mode on a repository with required checks, when the PR is not behind a merge queue, the landing drain stays at `3600000`. The required-checks wake runs `land`. The hour covers a merge that finishes after that run, and a PR that never posts a check.

## Pending requests

A child or launched thread can stall on a question for the user. `t3_pending_request_list` shows those and `t3_pending_request_read` shows one. Answer with `t3_pending_request_respond` only from facts and decisions the user already gave.

Approval (permission) requests are not listed and cannot be answered by these tools. A child stalled on one looks idle in `task_status`. Avoid the stall: children inherit this thread's runtime mode, so a child that must run commands or edit needs a parent in a mode that allows it. If a child stalls anyway, tell the user which thread is waiting for approval. Never raise a child's `runtimeMode` to get around it.

## ACP fallback

Some ACP agents accept the injected MCP server but do not expose its tools. When the T3 tools are absent and `T3_ACP_MCP_NODE` is set, call the same tools through the terminal:

```bash
ELECTRON_RUN_AS_NODE=1 "$T3_ACP_MCP_NODE" ${T3_ACP_MCP_ENTRYPOINT:+"$T3_ACP_MCP_ENTRYPOINT"} acp-mcp-call orchestrator_capabilities '{}'
ELECTRON_RUN_AS_NODE=1 "$T3_ACP_MCP_NODE" ${T3_ACP_MCP_ENTRYPOINT:+"$T3_ACP_MCP_ENTRYPOINT"} acp-mcp-call delegate_task '{"task":"...","mode":"async","clientRequestId":"..."}'
```

This is the supported transport, not a shell substitute for delegation.

## Outside T3

If neither the tools nor the ACP bridge exist, you are not running in T3. Use the host's native subagents on inherited models, run panels sequentially if needed, and state that model diversity and scheduling were unavailable.

## Skill locations

T3's `$` picker lists each provider's native skills, except Muse's. Muse still loads its own skills. Run `muse skills` in the terminal to manage them. A skill meant for every provider is written once and linked into each directory.

| Provider | User | Project |
| --- | --- | --- |
| Claude | `~/.claude/skills` (or `$CLAUDE_CONFIG_DIR/skills`) | `.claude/skills` |
| Codex | `~/.agents/skills` | `.agents/skills` |
| Grok | `~/.grok/skills` | `.grok/skills` |
| Cursor | `~/.cursor/skills` | `.cursor/skills`, and it also reads `.agents/skills` and `.claude/skills` |

Every child gets the `t3-code` server. Other MCP servers come from each provider's own configuration, so a child on another provider may lack one. A brief that needs a specific MCP server says so, and the child reports `MCP unavailable` instead of guessing.

## Personas

- `agents/poteto-agent.md` is the persona for code-writing delegates inside a poteto-mode playbook. Paste its body at the top of the child's brief, paste the `roles.py mode` lines, and run `roles.py check-brief` per [Delegation](#delegation) step 4.
- `agents/comment-sicko.md` is the persona for the no-comments review. Paste its body at the top of that reviewer's brief.
- Paste the body only, without the frontmatter.
