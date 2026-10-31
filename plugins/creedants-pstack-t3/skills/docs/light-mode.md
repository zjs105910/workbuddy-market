# Light mode

This is the design of the light mode setting in pstack-t3, which has shipped. Light mode is one setting, `full` or `light`. The user chooses it at start and can change it later. It cuts the model usage of poteto-mode playbooks and brigade coordinators and keeps the checks that catch real bugs.

The intended readers are a user who runs low on a provider's usage budget, and the engineer who builds the changes below.

**Status.** The setting is on `main`. Changes 1 to 5 landed as #81, #83, #84, #85, and #88. Change 6, the measured trial, finished on 2026-10-10. [Results](#results) records it. The trial found that the `medium` cap misses blocking findings, so the gate review keeps its full level in light mode. The passages below that cap the gate at `medium` describe the design as it stood before that decision, and the code and skills still apply the cap until a follow-up change removes it. The sections below keep the design as it was written before those changes landed, including its line numbers and its census of that time.

In this document a coordinator is one standing brigade coordinator thread and its store directory. A work item is one unit of work handed to a worker. An attempt is one worker run on a work item. brigade's commands and files keep their kitchen names only where they name a command or a file, such as `fire`, `dishes.tsv`, and `restaurant.json`.

## Summary

Light mode keeps every gate that decides whether code lands, and cuts the fan-out around it.

| Kept in light mode | Cut or cheapened in light mode |
| --- | --- |
| Unit tests and the build gate (`land.py` contract checks, CI) | The architect panel shrinks to one runner, with no cross-judge and no second `how` |
| The landing queue's checks and its linear-history and lease checks | `how` takes the simple path only |
| One review by a different model family at every head SHA before merge, brigade or standalone | `why` keeps the source-control investigator, and the parent writes the synthesis |
| The owner fences: leases, `--owner` generations, worktrees, the pass-at-head gate | Comment Sicko and the trail reviewer fold into the worker and the gate review |
| A fresh worker for every send-back | A fix attempt waives the design and investigation steps its playbook and attempt kind name |
| One executing fresh-child test per changed spawn behavior | Second reviewers, arena, interrogate, reflect, and extra fresh-child tests |
| The code delegate, so the author is never the diff's only reader | Fan-out waves are capped at 3 children |
| | Reasoning is capped at `medium` unless an explicit budget says otherwise |

On this repository's history, light mode would cut the child activity of a typical Feature change from about 610 items to about 240. It would cut a typical Bug fix from about 530 to about 280. That is a 47 to 60 percent cut in the measured unit, before the reasoning cap. A second set of per-child means gives 45 to 53 percent. See [Saving per change](#saving-per-change) for the method and its limits.

Light mode escalates a work item to `full` in three cases. Its lease covers a configured high-risk path. It has two send-backs in `pass.tsv`. Or the coordinator recorded the design as contested with `brigade.py dish --mode full`. On this repository the configured paths are `land.py`, `brigade.py`, and `install.py`. That rule alone escalates 34 of 69 merged items. 32 of them changed one of those scripts, and D5 and D11 held a directory lease over one. Light mode therefore applies to about half of this repository's items.

[Changes](#changes) lists six changes in landing order.

## Method

Five sources fed the census and the estimates.

1. The skill sources under `t3/`. A search for every `delegate_task`, `t3_thread_launch`, and `create_threads` call, and every routed skill call, then a read of each child's brief recipe. Line numbers are in those sources, not in the generated `skills/`. The search command is in [Appendix A](#appendix-a-commands).
2. The pstack-t3 coordinator store at `~/.local/state/pstack-t3/brigade/pstack-t3/pstack-t3`. The snapshot is every merged item with an id up to D72, which is 69 items. `pass.tsv` holds 129 verdicts on those items. The live files hold later rows, so every command filters to merged items up to D72.
3. T3 thread activity for 10 sampled work items, read with `t3_thread_read`. Each child thread's `itemCount` is the size unit. It counts messages, reasoning blocks, tool calls, and checkpoints on the child's timeline. The sample and its selection rule are in [Appendix C](#appendix-c-sampled-child-activity).
4. Every send-back review report, each classified as a real bug, an instruction or doc gap, or a style nit. The classification is in [Appendix B](#appendix-b-send-back-classification).
5. The squash commit of every merged item on `main`, matched by the `(#N)` suffix of its subject, for the files each item changed.

T3 records no token counts and no reasoning level on a thread. Activity items are the closest measured size, and they undercount a long reasoning block. Every cost figure in this document is in activity items or child counts. Every ratio is an estimate in that unit.

## Usage census

### What a work item costs today

The snapshot holds 69 merged work items. This document counts an attempt as one gating verdict in `pass.tsv`. That is a count, not a code invariant. A worker replacement or a queue bounce launches another worker thread without a verdict, and `log.tsv` holds 227 `in-progress` rows for these 129 verdicts.

| Measure | Median | Mean | p90 |
| --- | --- | --- | --- |
| Attempts per merged item | 2 | 1.87 | 3 (max 6, D24) |
| Send-backs per merged item | 1 | 0.86 | 2 (max 5, D24) |
| Worker run, in progress to in review | 12.8 min | 17.8 min | 30.7 min |
| Review, in review to verdict | 5.2 min | 6.6 min | 11.2 min |
| Work item, first start to merged | 41.9 min | 56.8 min | 118.5 min |

25 items passed their first review, 33 needed two attempts, 8 needed three, 2 needed four, and D24 needed six. 59 of 129 verdicts were send-backs.

In the 10 sampled work items, worker-side children produced 2290 activity items over 82 threads. Coordinator-side children produced 2082 over 29 threads. D64 alone holds 1005 of the coordinator-side items, from second reviewers and usage-limit replacements. The coordinator thread itself has 519 runs and 5076 items since 2026-10-05. That is a standing cost and not a per-item cost.

### Spawn points

Each row is one place a skill spawns a child or a thread. "Items" is the mean `itemCount` of that child in the sample, or `n/s` when the sample holds none. Seats are the live `~/.config/pstack-t3/roles.json` on this machine. It seats five `architect runners`, five `arena runners`, five `interrogate reviewers`, and seven `verifiers`. The built-in defaults seat two in each of the first three panels.

**Routed skills.**

| # | Spawn | Source | Children per run | When | Items |
| --- | --- | --- | --- | --- | --- |
| 1 | `how`, simple path | `t3/overrides/how/SKILL.md:17`, `:32` | 1 explainer, `how explainer` | A narrow question, and every doubtful one | 19 |
| 2 | `how`, complex path | `how/SKILL.md:18`, `:24`, `:42` | 2 to 4 `how explorer`, then 1 explainer | A multi-file or cross-cutting question | n/s |
| 3 | `why` investigators | `t3/overrides/why/SKILL.md:81`, `:97` | 1 per evidence category with a source. Source control always | Bug fix step 2, recall (`recall/SKILL.md:20`), teach, motivation questions | 150 for two |
| 4 | `why` synthesizer | `why/SKILL.md:128` | 1 | After the investigators | 14 |
| 5 | `architect` grounding | `t3/overrides/architect/SKILL.md:23` | a second `how` run | Every non-greenfield architect run | 19 |
| 6 | `architect` runners | `architect/SKILL.md:31`, `:45` | 1 per `architect runners` seat. 5 live, 2 built in | Feature step 2. Bug fix, Refactoring, Perf when the change crosses a function boundary. figure-it-out for a one-way door. A scrapped design reruns rows 5 to 7 (`architect/SKILL.md:86`) | 164 per 5-seat panel |
| 7 | Arena cross-judge | `t3/overrides/arena/SKILL.md:50` | 1 from `arena cross-judge pool` | After every arena and architect panel | 27 |
| 8 | Arena candidates | `arena/SKILL.md:36`, `:42` | 1 per `arena runners` seat | Feature step 4 in place of the code delegate, blast-radius step 6, Eval step 4 (`eval.md:20`) with a blinded judge (`:21`) | n/s |
| 9 | Code delegate | `feature.md:12`, `bug-fix.md:9`, `refactoring.md:11`, `perf-issue.md:17`, `hillclimb.md:12` | 1, or 1 per live hypothesis in Hillclimb | Every code-writing playbook | 53 |
| 10 | Comment Sicko | `t3/overrides/no-comments/SKILL.md:19` via `opening-a-pr.md:9` | 1 on `judgment and prose` | Before review, at the end of every playbook that opens a change | 8 |
| 10a | Comment Sicko follow-ups | `no-comments/SKILL.md:20`, `:21` | a `how` or `why` run for a thin keep, 1 rerun of a rejected report, 1 `architect` run when a fix needs a shape | When the report triggers them | n/s |
| 11 | `interrogate` | `t3/overrides/interrogate/SKILL.md:44` | 1 per `interrogate reviewers` seat | Feature step 7 when contested, a child that opens a PR (`opening-a-pr.md:38`), optionally inside architect (`architect/SKILL.md:59`) | n/s |
| 12 | Fresh-child skill test | `t3/added/pstack-author-skill/SKILL.md:53` to `:56` | 1 per test, a new child per retry, 1 more on another provider | Every change to a skill's behavior (house rule 7) | 10 as a leaf. 70 to 111 when the test runs a playbook |
| 13 | Description eval | `pstack-author-skill/SKILL.md:61` | 5, plus a rerun per failure | When triggers are uncertain | n/s |
| 14 | `swarm` workers | `t3/overrides/swarm/SKILL.md:24`, `:39` | N from the user or the shape, plus 1 respawn per bad result | Explicit swarm | n/s |
| 15 | Trail reviewer | `t3/overrides/show-me-your-work/SKILL.md:67` | 1, another family than the worker | Hand-back of every run with a decision trail. Called by Autonomous run (`autonomous-run.md:10`), Hillclimb (`hillclimb.md:9`), Autopilot owners, and Orchestrate close (`orchestrate.md:67`) | 17 (two runs outside the sample) |
| 16 | `reflect` | `t3/overrides/reflect/SKILL.md:27`, `:39` | 3 reviewers, then 1 synthesizer | The user says reflect, and brigade's weekly service in full mode (`t3/added/brigade/SKILL.md`, Run a service step 8) | n/s |
| 17 | Recall slices | `t3/overrides/recall/SKILL.md:19` | 1 per slice of the thread list, no fixed N | Every recall over more than two threads | n/s |
| 18 | Automate-me miners | `t3/overrides/automate-me/SKILL.md:31` | 1 per history slice, 3 in the example | Every automate-me run | n/s |
| 19 | Verification source wave | `t3/overrides/maintain-verification-skill/SKILL.md:29` | 1 per feature file, no cap | Every maintenance pass | n/s |

**poteto-mode playbooks.**

| # | Spawn | Source | Children per run | When | Items |
| --- | --- | --- | --- | --- | --- |
| 20 | Multi-phase exploration | `multi-phase-plan.md:7` | several read-only explorers, no count | Before the plan, unless the change is one or two files (`:5`) | n/s |
| 21 | Multi-phase lanes | `multi-phase-plan.md:13`, checklist at `:65` | at least 14 per code-ready head. 1 gates, 10 live, 1 perf, 2 audit | Executing a multi-phase plan | n/s |
| 22 | Autopilot owner | `autopilot-full.md:6`, `autopilot-stack.md:5` | 1 `t3_thread_launch` per PR, a fresh one per next item (`autopilot-full.md:9`) and per stuck owner (`:10`) | Every Autopilot program | n/s |
| 23 | Autopilot swarm-verify | `autopilot-full.md:8`, reused by `autopilot-stack.md:8` | at least 5 lanes per code-ready head. Gates, live, two audit, regression | Every Autopilot round whose patch-id changed | n/s |
| 24 | Orchestrate sub-coordinator | `orchestrate.md:16` | 1 per track, each spawning its own workers | Only when one coordinator cannot drain the program | n/s |
| 25 | Orchestrate worker | `orchestrate.md:17` | fewer, broader workers, one writer per branch | Every unit | n/s |
| 26 | Orchestrate long-lived owner | `orchestrate.md:18` | 1 `t3_thread_launch` per stacker, babysitter, or PR owner | Owners that outlive one turn | n/s |
| 27 | Orchestrate verifier | `orchestrate.md:88` | 1 on `verifiers` | Only when verification is expensive, judgment-laden, or high-blast-radius | n/s |
| 28 | Shipping verifier | `shipping.md:7` | 1 per PR on one `verifiers` seat | Shipping a green stack | n/s |
| 29 | Visual parity owner | `visual-parity.md:7` | 1 child per component, each in its own worktree | Every visual parity migration | n/s |
| 30 | Worktree cleanup summarizer | `worktree-cleanup.md:7` | 1 per long thread the parent will not read | Only for long threads | n/s |
| 31 | Autonomous run watcher | `autonomous-run.md:6` | 1, only when the wake is not a pull request event | Long runs | n/s |

**brigade, landing, and setup.**

| # | Spawn | Source | Children per run | When | Items |
| --- | --- | --- | --- | --- | --- |
| 32 | Coordinator thread | `t3/added/brigade/SKILL.md`, Open a restaurant step 6 | 1 `t3_thread_launch` | `open` printed `opened` | standing |
| 33 | Executive admin thread | `t3/added/brigade-admin/SKILL.md:33` | 1 `t3_thread_launch` | `open --admin` printed `opened` | standing |
| 34 | brigade worker | `t3/added/brigade/SKILL.md`, Run a service step 4.3 | 1 top-level thread per attempt | When the item is neither held nor awaiting a round decision, its first attempt and replacements after a queue bounce or a send-back (Run a service step 7), a missing worker (Liveness check, the `in progress with no worker thread` line), and a timebox replacement (Liveness check step 4) | 29 to 354 per worker |
| 35 | brigade gate verifier | `t3/added/brigade/SKILL.md`, Run a service step 6 | 1 from `verifiers` by default, another family than the author | Completed attempts that are neither held nor contested, at their head SHA | 38 |
| 36 | brigade second reviewer | not in the skill text | 1 trial model | 19 times, on D59 to D70 during the reviewer trial | 110 |
| 37 | brigade fix-the-recipe | `t3/added/brigade/SKILL.md`, Run a service step 8 and Liveness check step 2 | 1 work item on the `correct` skill | Two items repeat one mistake, or Liveness check step 2 sees `report written, no report-back` | as one work item |
| 38 | Landing writer | `t3/added/landing/SKILL.md:85` | 1 per writing unit, a thread for a long run, else a child | Each unit a coordinator lands | as rows 34 or 9 |
| 39 | Landing queue | `t3/added/landing/scripts/land.py` (`Integration.check`, `land`) | 0. Subprocess checks and `gh` reads only | Every submitted entry | 0 |
| 40 | Setup smoke test | `t3/setup.md:68` | 1 per distinct provider in the roles table, `mode: "wait"` | Setup only | n/s |

Skills that only route to these rows map onto them. `teach` runs rows 1 to 4. `blast-radius` runs row 8 for a wide change. `figure-it-out` runs rows 5 to 7. `poteto-help:56` and the reflect reviewer prompts mention `delegate_task` without spawning. No skill calls `create_threads`.

A Feature attempt is rows 1, 5, 6, 7, 9, and 10. A Bug fix attempt is rows 1, 3, 4, 9, and 10, plus rows 5 to 7 when the fix crosses a function boundary. Row 12 joins either one when the change edits a skill's behavior. `pass.tsv` records only rows 34 and 35. Every other row is visible only as a child thread.

### Where the items went

The sampled first attempts of Feature work show the shape.

| Work item | `how` | Architect panel and judge | Code delegate | Comment Sicko | Skill tests | Total |
| --- | --- | --- | --- | --- | --- | --- |
| D1 | 29 | 227 | 51 | 0 | 0 | 307 |
| D50 | 20 | 176 | 53 | 0 | 0 | 249 |
| D70 | 26 | 260 | 77 | 8 | 46 | 417 |

The architect panel and its judge took 62 to 74 percent of the worker-side items on every sampled Feature attempt. The code delegate took 17 to 21 percent. Comment Sicko is the cheapest child in the census.

Bug fix attempts put the weight on `why`. D71's first attempt spent 111 of 187 items on two `why` investigators. D72's retry spent 202 of 343 on three, and repeated a 5-seat architect panel for a one-paragraph change.

Send-backs repeat the whole tree. A fresh worker reruns the playbook from step 1, so a fix attempt costs about what a first attempt costs. D72's retry (343 items) cost more than its first attempt (216). Two sampled fix attempts, D24's sixth and D65's second, spawned no children at all. The fan-out is already uneven in practice.

## The setting

### Where it lives

The setting is one key, `"mode"`, with the values `"full"` and `"light"`, in the files that already hold `"budget"`. A missing key reads as `full`.

| Level | Where | Written by |
| --- | --- | --- |
| User | `~/.config/pstack-t3/roles.json` | `setup-pstack`, `roles.py write --mode` |
| Project | `<repo>/.pstack/t3-roles.json` | `setup-pstack --project`, `roles.py write --project --mode` |
| Coordinator | `<store>/restaurant.json` | `brigade.py open --mode`, `brigade.py set --mode` |
| Session | the user's words, such as `$poteto-mode light`, "light mode", or "full mode" | the user, for that thread only |
| Brief | a `Mode:` line in a child's brief | the parent that wrote the brief |

### One effective mode

The highest level present wins. The order is brief, then session, then coordinator, then project, then user, then `full`.

`roles.py` owns this order, as it owns roles. One function, `effective_mode`, takes the merged config and three optional inputs. Two commands share it.

- `roles.py show` and `roles.py mode` both accept `--brief-mode`, `--session-mode`, and `--coordinator-mode`, each `full` or `light`. Both print `"mode"` and `"modeSource"`. `show` then resolves every seat under that mode.
- `--brief-mode` is the frozen decision. A child copies the value of its brief's `Mode:` line into every `roles.py` call it makes, and passes no other mode input. The child never resolves the mode again, so a project file that says something else cannot change it.
- A parent writes `Mode: <effective mode>` into every brief whose child resolves seats or spawns. That covers brigade workers, code delegates, Autopilot and Orchestrate owners, sub-coordinators, unit workers, visual-parity owners, landing writers, and fresh-child tests that run a playbook. Read-only leaves such as a `how` explainer get no line, because they resolve nothing.
- A session in light mode passes `--session-mode light` to every `roles.py` call it makes, and writes `Mode: light` into its children's briefs.

The brief has to carry the decision because a child may not see the project file. `.gitignore` lists `/.pstack/`, so a new worktree has no `.pstack/t3-roles.json`, and `project_config_path` stops at the worktree's `.git` file. A worker that ran `show --cwd` in its worktree would read only the user file. For the same reason `roles.py mode` runs in the coordinator's checkout, where the project's `escalate` list lives.

The coordinator resolves the worker's `modelSelection` when it launches the worker (`t3/added/brigade/SKILL.md`, Run a service step 4.3) and the gate verifier's seat when it launches the verifier (step 6). It resolves both with `show --brief-mode <the item's mode>`, never with `--coordinator-mode`, so an escalated item's worker and gate get full seats.

So a coordinator set to `light` over a project set to `full` writes `Mode: light` into its worker's brief. The worker runs `roles.py show --brief-mode light`, and every seat it and its delegates resolve gets the light cap. A child escalated to `full` under a project set to `light` gets `Mode: full`. Its `roles.py show --brief-mode full` applies no light cap.

### The reasoning cap

When the effective mode is `light` and the merged budget is `default`, `show` resolves seats as budget `small`. `t3/scripts/roles.py:43` maps `small` to a `medium` reasoning cap. An explicit budget wins in both directions. `light` with `large` keeps xhigh seats, and `full` with `small` keeps the `medium` cap it already has. Under budget `small`, an `inherit` seat already becomes an explicit target with the capped option (`inherit_with_budget`), so a light child cannot pass its parent's xhigh through. That conversion needs a catalog and the right parent. Without a catalog, `resolve` caps nothing. With a catalog and no `--parent`, explicit seats are capped, but an `inherit` seat either stays `inherit` (the saved snapshot clears the parent) or converts against the catalog's saved parent (`--catalog` keeps it). Under `light`, `show` without a catalog or without `--parent` prints an `info` line that the `inherit` cap may be wrong. The runtime's Roles section already requires both.

The cap is the only option light mode changes. Light mode never sets `fastMode` to true. In both modes, a Grok seat on a model that declares `fastMode` comes back from `show` with `"fastMode": false`, and that includes a seat that falls back to the built-in Grok default. [The runtime's Excluded seats](../t3/runtime.md#excluded-seats) states the rule.

An escalated item resolves as `full`, so it keeps its full reasoning level. The saving estimate counts no reasoning saving for escalated items.

This replaces the prose budget line in brigade's `menu.md`, which no script reads. The live pstack-t3 menu says `medium` while the roles file says `default`.

### Escalation

`roles.py mode` decides escalation from inputs it can compute when brigade writes a brief. Escalation only moves toward `full`.

1. **A high-risk path.** The project file's `"escalate"` key lists path patterns. There is no built-in default, because a guessed default fires on paths like `t3/overrides.lock.json`. `setup-pstack --project` suggests `**/migrations/**` and the project's own lock and installer scripts. For pstack-t3 the list is `t3/added/landing/scripts/land.py`, `t3/added/brigade/scripts/brigade.py`, and `scripts/install.py`.
2. **A second send-back.** `roles.py mode --send-backs <n>` escalates at 2. brigade counts `n` from the item's `send-back` rows in `pass.tsv`, never from the attempt number. A replacement worker or a queue bounce adds an attempt without a send-back.
3. **A contested design.** A light worker that finds its design contested does not run `interrogate`, because its brief waives it. It stops at a verifiable point and reports `Contested: <reason>` under its status. The coordinator then records the escalation and launches a fresh worker in `full` with that report. The new attempt is a replacement, not a send-back, so the gate never sees a contested design that skipped interrogate. The coordinator records it with `brigade.py --owner <thread>@<generation> dish <item> --mode full --reason "<text>"`, inside the existing fenced `dish` write. It does this at fire time when the tickets name a lock, a lease, a race, a migration, or history rewriting, or after a worker's report says `Contested: <reason>`. `fire --mode full --reason "<text>"` is the same record at creation.

The path rule has exact semantics.

- **Normalization.** A lease path or pattern goes through `land.py`'s `canonical`, the function that already normalizes leases. The result is POSIX and relative to the repository root. Backslashes become `/`, `normpath` runs, and then a leading `/` drops. So `a/../b` is `b` and `/../x` is `x`, while `../x` is an error. An empty result is the repository root.
- **Pattern match.** Patterns match whole segments. `**` matches zero or more segments. Inside one segment, `*`, `?`, and `[...]` follow `fnmatch.fnmatchcase` and never cross a `/`.
- **Coverage.** A lease covers its own path and every tracked file under it, from `git ls-files` in the coordinator's checkout when the brief is written. A file lease therefore covers one path, tracked or new. A directory lease covers its tracked descendants. The root lease covers every tracked file.
- **Rule.** The item escalates when any covered path matches any pattern.

The escalation is durable. When rule 1, 2, or 3 first fires, `brigade.py` appends a `log.tsv` row with kind `mode`, the item's id, state `full`, and the reason as its note. It appends under the store lock and the `--owner` fence, like every other store write. `log.tsv` is append-only and needs no new column, so existing stores need no migration. Every later `brief` for the item reads its latest `mode` row first and passes `--escalated "<reason>"` to `roles.py mode`. A later change to the coordinator, project, or user setting cannot return the item to `light`. Nothing moves an item from `full` to `light` mid-flight.

`roles.py mode` prints the result in brief grammar, as in [Brief lines](#brief-lines).

On this repository's 69 merged items, rule 1 escalates 34. Those items carried 35 of the 59 send-backs and 18 of the 24 items whose reviews found a real bug. Rule 2 adds D16, D23, D25, D49, and D63 at their third attempt.

The previous draft proposed narrower leases for skill text so that rule 1 would fire less. Checking each item's squash commit against the three scripts shows that would not help. 32 of the 34 escalated items changed one of those scripts. Only D5 and D11 escalate through a directory lease without touching one. D11 was sent back for a merge wait that hangs. The design drops that change.

### How the user picks it

- **At setup.** `setup-pstack` asks for the mode right after the budget, with the host's question tool, and names the current value. The options are `full`, recommended when no provider is near its limit, and `light`. `roles.py write --mode` saves it.
- **When opening a coordinator.** brigade's Open step asks for the mode with the reporting level. `brigade.py open --mode light|full` records it in `restaurant.json`. Leaving it out records nothing, so the project and user files decide.
- **For one session.** `$poteto-mode light` or "use light mode" in a request sets the session level. "full mode" sets it back.

### How it changes later

- `brigade.py set --mode light|full` changes a coordinator. `set --mode ""` returns it to the project and user files. The change applies to the next brief. A running attempt keeps the mode its brief names.
- `roles.py write --mode` changes the user or project file. New sessions read it. A running coordinator reads it at its next brief.
- When a provider in the `verifiers` or code roles hits its usage limit, the coordinator first relaunches or resumes the failed worker or verifier with `roles.py backup`, per [Failure handling](../t3/runtime.md#failure-handling). The mode stays as it was. The coordinator does not switch modes on its own. Whatever `backup` prints, it then parks the choice with `86 add`, defaulting to `light` until the limit resets. It switches only when the user answers or the menu's `## Budget` says to. A usage limit is the user's budget call. Codex hit its limit three times on 2026-10-07 (D64, D70, D71 in `pass.tsv`) without anyone changing a setting.

### What the agent says

When light mode applies, the thread says so once, at the start, in two or three short sentences. "Light mode is on, from this coordinator's setting. This change gets one design sketch and no separate comment review. Tests, the build, and a review by another model family still run."

On an escalation it names the rule. "This change runs in full mode because its lease covers `land.py`."

The worker report repeats the brief's `Mode:` and `Waived by mode:` lines under its status. Steps waived by the mode are not deviations. The coordinator's digest replies name the mode only when it changes.

## What light mode changes

Each row maps to the census row it changes. "Merged" means two passes become one. "Cheaper seat" means the same step on a lower reasoning level.

| Census row | Full | Light | Kind |
| --- | --- | --- | --- |
| 1 `how` simple | 1 explainer | 1 explainer | Kept |
| 2 `how` complex | 2 to 4 explorers and 1 explainer | 1 explainer, simple path always | Cut |
| 3 `why` investigators | 1 per category | Source control only | Cut |
| 4 `why` synthesizer | 1 child | The parent writes the synthesis | Merged |
| 5 `architect` grounding | A second `how` run | Reuses the playbook's `how` output | Merged |
| 6 `architect` runners | 1 per seat | 1 runner on the first `architect runners` seat, asked for two structurally distinct sketches | Merged |
| 7 Cross-judge | 1 child | The parent picks. The gate review reads the chosen design | Cut |
| 8 Arena | 1 per seat and a judge | The single code delegate. Eval keeps arena, because comparing candidates is its whole purpose | Cut |
| 9 Code delegate | 1 | 1. Hillclimb runs one live hypothesis at a time | Kept |
| 10 Comment Sicko | 1 child | The worker applies the no-comments rules to its diff. The gate review's brief adds the comments check | Merged |
| 10a Comment Sicko follow-ups | `how`, `why`, rerun, `architect` | None. A finding that needs them goes into the gate's verdict as a send-back | Cut |
| 11 `interrogate` | 1 per seat | Not run. A contested design escalates to `full`. Outside brigade, the gate review replaces the PR-opening child's run | Cut |
| 12 Fresh-child test | 1 per test, plus one on another provider | See [Fresh-child tests in light mode](#fresh-child-tests-in-light-mode) | Cheaper seat |
| 13 Description eval | 5 children | Only when the change edits a `description` | Cut |
| 14 `swarm` | N workers | At most 3 workers | Cut |
| 15 Trail reviewer | 1 child | Folded into the gate review when one runs at that head. Otherwise kept as the gate | Merged |
| 16 `reflect` | 3 and 1 | brigade's weekly reflect is skipped. A user's explicit reflect runs in full | Cut |
| 17 Recall slices | 1 per slice | At most 3 slices, and no `why` wave unless asked | Cut |
| 18 Automate-me miners | 1 per slice | 1 miner over the whole window | Cut |
| 19 Verification source wave | 1 per feature file | At most 3 children, each reading a batch of feature files | Cut |
| 20 Multi-phase exploration | several | 1 explorer | Cut |
| 21 Multi-phase lanes | 14 or more | Gates, one live lane per surface, and one audit lane on another family | Cut |
| 22 Autopilot owner | 1 per PR | 1 per PR, with `Mode: light` in its brief | Kept |
| 23 Autopilot swarm-verify | 5 or more lanes | 2 lanes. Gates, which keeps the patch-id rule, and one audit lane on another family that is the gate review and runs at every new head SHA | Cut |
| 24 Orchestrate sub-coordinator | 1 per track | 1 per track, with `Mode: light` in its brief | Kept |
| 25 Orchestrate worker | fewer, broader | Same, with `Mode: light` in each brief | Kept |
| 26 Orchestrate long-lived owner | 1 per owner | Same, with `Mode: light` in each brief | Kept |
| 27 Orchestrate verifier | When expensive | When expensive. A cheap unit's merge still needs the gate review at its head | Kept |
| 28 Shipping verifier | 1 per PR | 1 per PR. It is the gate review, and it reuses only a current qualifying pass at the PR's exact head SHA | Kept |
| 29 Visual parity owner | 1 per component | 1 per component, at most 3 in flight, with `Mode: light` in each brief | Cut |
| 30 Worktree cleanup summarizer | 1 per long thread | None. The parent reads the last page of each thread with `t3_thread_read` and `limit` | Cut |
| 31 Autonomous run watcher | 1 | 1 | Kept |
| 32 Coordinator thread | 1 | 1 | Kept |
| 33 Executive admin thread | 1 | 1 | Kept |
| 34 brigade worker | 1 per attempt | 1 per attempt, reasoning capped at `medium` | Cheaper seat |
| 35 Gate verifier | 1 per attempt | 1 per attempt, same seat, reasoning capped at `medium` until [Change 6](#change-6-a-measured-light-mode-trial) decides | Cheaper seat |
| 36 Second reviewer | Trials | Never | Cut |
| 37 Fix the recipe | A `correct` work item | Filed as a ticket and run when the mode returns to `full` | Cut |
| 38 Landing writer | 1 per unit | 1 per unit, with `Mode: light` in its brief | Kept |
| 39 Landing queue | Checks | Checks | Kept |
| 40 Setup smoke test | 1 per provider | 1 per provider. Setup runs once, and a failed smoke test is the only proof a seat works | Kept |

A send-back in light mode is a fix attempt with a fresh worker. Its brief carries the findings and waives the steps [Waivers](#waivers) names.

### Never cut

- **Tests and the build gate.** The worker runs `python3 -m unittest discover -s tests` and `python3 scripts/build.py` through `land.py slot --`. The queue reruns them.
- **The landing queue's checks.** `land.py` spends no model usage. Light mode has nothing to gain there.
- **One review by another model family at every head SHA.** [The gate review](#the-gate-review) defines it for brigade and for standalone playbooks.
- **Re-review of every fix attempt over its whole diff.** Three later rounds caught a real bug that round 1 missed in the same diff (D42, D55, D61). A fix attempt's review reads the full diff against trunk, not only the delta.
- **Owner fences.** Leases, the `--owner` generation, worktrees, and the pass-at-head gate are code, and they cost nothing.
- **A fresh worker for every send-back.** See [The fresh-worker rule](#the-fresh-worker-rule).
- **The code delegate.** The persona and `Playbook:` line still apply, and `roles.py check-brief` still gates the brief.
- **One executing fresh-child test per changed spawn behavior.** See [Fresh-child tests in light mode](#fresh-child-tests-in-light-mode).

### The gate review

Light mode has one gate review per head SHA before merge. It is one read-only child on a `verifiers` seat whose model family differs from the author's. The author is the code delegate's model, or the worker's when it wrote code itself. The gate reads the whole diff against its base. Its brief adds three checks that folded children used to run.

- The no-comments rules from `agents/comment-sicko.md`, applied to the diff.
- The chosen design, when the light architect step picked one of two sketches.
- The decision trail, when the run kept one per `show-me-your-work`. The gate reads the log and the run's thread and keeps that skill's checks. It flags weak evidence, skipped or unproven verification, misleading readiness, and a shell success that hides a failed check.

The gate's verdict is `pass`, `send-back`, or `blocked`, with the head SHA, the author, and the verifier.

**In brigade** the gate is the existing verifier (`t3/added/brigade/SKILL.md`, Run a service step 6). The coordinator records it with `pass record`, and `dish --state queued` refuses a SHA without a pass. A brigade worker's brief carries `Gate: brigade`, and the worker runs no gate of its own.

**In a standalone playbook** (Feature, Bug fix, Refactoring, Perf issue, Hillclimb, Visual parity, Authoring a skill), Opening a PR runs the gate before it opens or marks the PR ready. Full mode has no such gate today. Feature, Bug fix, Refactoring, and Perf issue end with the parent's own read of the diff, and Opening a PR seats no `verifiers`. Light mode adds the gate because it removes the panels that gave full mode its diversity.

The standalone gate reuses a current qualifying pass instead of launching a duplicate. Reuse is by exact head SHA only.

- **Current.** The verdict is the latest one for that item at that SHA. A later `send-back` or `blocked` at the same SHA voids an earlier pass, as it does in `pass_check` (`brigade.py:790`).
- **Qualifying.** The verdict is `pass`, and its author and verifier are of different families.

Two sources can show both today.

1. **brigade's `pass.tsv`.** The parent runs `brigade.py pass check <item> --sha <head> --json`, added in [Change 5](#change-5-brigades-mode). It selects the row with the same code as `pass_check`, which `dish --state queued` already uses, and prints `verdict`, `author`, `verifier`, `note`, and `crossFamily`. `crossFamily` is false when `record_pass`'s family rule finds one family, or when the note starts with `same model family`. The parent reuses the pass only when the command exits 0 and prints `"crossFamily": true`. The parent never reads `pass.tsv` itself, and never takes the text of today's `pass check` as proof. That text names the verifier on success and neither identity on failure.
2. **A verdict this run launched at that exact SHA.** It must be the latest verdict this run holds for that SHA. A Shipping or Autopilot root's own verdict at that SHA counts.

These do not qualify.

- An Orchestrate `ledger.tsv` row. Its verdicts are verification levels, not `pass`, and it records no author (`orchestrate.md:90`).
- A Shipping or Autopilot verdict from another run. It lives only in that root thread's messages.
- A verdict at another head SHA, even when the two heads' `git patch-id` match. A patch-id ignores whitespace, so a matching patch-id does not prove the same behavior. The second review of this design ran `git patch-id --stable` on two Python patches that add the same `raise RuntimeError("broken")` line with different indentation. Both printed one patch-id. One function returned `ok`, and the other raised.

Full mode keeps its own patch-id policy unchanged. Shipping (`shipping.md:9`), Autopilot-full (`autopilot-full.md:8`, `:9`), and Autopilot-stack (`autopilot-stack.md:11`) keep a code verdict across a head whose patch-id matches. Light mode does not apply that policy to the gate review. Light mode keeps it for lane receipts. A Shipping or Autopilot root in light mode may still reuse a tests, build, or mergeability result wherever `shipping.md:9` allows, and reruns the rest as that rule says. A lane receipt never stands in for the gate review. At a new head SHA the root launches a new gate review unless a current qualifying pass exists at that exact SHA.

This costs one gate review per rewritten head. An Autopilot-stack rebase rewrites every SHA above it, so a light stack pays one gate per rewritten PR where full mode keeps the verdict. Light mode accepts that cost, because it removed the panels and lanes that give full mode its other review coverage.

The parent records the verdict it used in the PR body's `## Verification` section as one line, `Gate: pass at <short sha> by <provider/model>`. The SHA is the PR's current head.

### Waivers

A waiver removes one named step for one attempt. `roles.py mode` prints the waivers from one table, `LIGHT_WAIVERS`, keyed by playbook and attempt kind. The attempt kinds are `first`, `fix` (after a send-back), and `bounce` (after a queue bounce). Step names are the playbook's own words.

| Playbook | `first` | `fix` and `bounce` |
| --- | --- | --- |
| Feature | Arena, Interrogate, Comment Sicko | How, Architect, Arena, Interrogate, Comment Sicko |
| Bug fix | Comment Sicko | How, Why, Architect, Comment Sicko |
| Refactoring | Comment Sicko | How, Architect, Comment Sicko |
| Perf issue | Comment Sicko | How, Architect, Comment Sicko |
| Hillclimb | Comment Sicko | How, Comment Sicko |
| Authoring a skill | Comment Sicko, Second-provider test | Comment Sicko, Second-provider test |
| Every other playbook | none | none |

Interrogate is a waiver only in Feature, where step 7 runs it for a contested design (`feature.md:16`). In light mode a contested design escalates instead. The other interrogate call, in a child that opens a PR (`opening-a-pr.md:38`), never runs inside brigade, whose worker brief forbids opening a PR. Outside brigade, light mode replaces it with the gate review, per row 11.

The Bug fix fix-attempt row waives Bug fix step 2's `how` and `why` seeds. The review's findings name the defect, so the worker confirms that mechanism with runtime evidence, which step 2's last sentence already requires, and goes to step 3. Step 1 still reproduces the finding. The sample supports the cut. D72's retry spent 202 of 343 items on three `why` investigators for a fix its review had already located.

A step that light mode reduces but does not remove is not a waiver. The single architect runner, the simple `how` path, and the source-control-only `why` are how those steps run in light mode, so a worker that runs them has skipped nothing.

### Brief lines

A brief carries these lines, each at most once.

```text
Playbook: playbooks/feature.md
Mode: light
Mode source: restaurant.json
Attempt: fix
Waived by mode: How, Architect, Arena, Interrogate, Comment Sicko
Gate: brigade
```

- `Mode:` holds only `full` or `light`. Nothing follows the value.
- `Mode source:` holds one of `brief`, `session`, `restaurant.json`, `.pstack/t3-roles.json`, `roles.json`, `default`, or `escalated: <reason>`. It is for people, and no command reads it.
- `Attempt:` holds `first`, `fix`, or `bounce`.
- `Waived by mode:` lists the waivers, comma-separated, in table order.
- `Gate:` holds `brigade` or `standalone`.

`roles.py mode` prints exactly these lines for an item, and `brigade.py brief` writes them unchanged.

### `roles.py check-brief`

`check-brief` validates the lines against the table, not against a global union.

- At most one of each line. `Mode:` is required in a code delegate's brief.
- `Mode:` is `full` or `light`.
- Under `Mode: full`, no `Waived by mode:` line.
- Under `Mode: light`, `Attempt:` is required, and `Waived by mode:` must equal `LIGHT_WAIVERS[(playbook, attempt)]` exactly. The playbook comes from the `Playbook:` line. A first-attempt Feature brief with `Waived by mode: How` fails, because How runs on a first attempt. A first-attempt Feature brief without Comment Sicko in its waivers fails too, so a compliant light worker is never sent back for skipping it.

### Interaction with Deadlines

The runtime's Deadlines rule (`t3/runtime.md:33`) says a timebox orders the work and never waives a step. brigade sends back a skip cited to the timebox (`t3/added/brigade/SKILL.md`, Run a service step 6). Light mode keeps that rule whole. A waived step is not a skip, because the mode removes it before the attempt starts and the brief records it.

The worker runs every playbook step its `Waived by mode:` line does not name, under the Deadlines rule as written. It never adds a waiver of its own. At review, the coordinator compares the report's skipped steps with that line. A skip the line names passes. Any other skip, including one cited to the timebox, is still a send-back. A mode change mid-attempt does not change the line. It applies to the next brief.

### The fresh-worker rule

A send-back launches a fresh worker with `t3_thread_launch` unless the item is held or owes its round decision (`t3/added/brigade/SKILL.md`, Run a service step 7). The rule exists so that a fix never inherits a stale context or drops a directive, and light mode does not weaken it. Light mode makes the fresh worker cheaper. Its brief carries `Attempt: fix`, the waivers from the table, the verifier's findings file, and the old branch head as its base. D24's sixth attempt and D65's second spawned no children and passed. D72's retry reran a five-seat panel for a one-paragraph change and cost more than its first attempt.

A queue bounce is not a send-back. Its fresh worker gets `Attempt: bounce` and the bounce reason. It does not count toward rule 2.

### Fresh-child tests in light mode

House rule 7 requires a fresh-child test for every change to a skill's behavior. D70's first review rejected tests whose briefs forbade spawning. They produced plans, but never executed How, the implementation delegate, or the parent's read check. D69's first review rejected records that did not cover the changed behavior. Light mode keeps both lessons.

- **A leaf test** runs on the `skill tests` seat and forbids spawning. It is allowed only when the changed behavior happens without delegation, such as a reply's wording, a brief line, or a command the skill runs.
- **An executing workflow test** runs the playbook with its real children, nested ones included. It is required once for each changed spawn or coordination behavior. One test covers one behavior. Two unrelated changed behaviors need two tests.
- The second-provider test is waived in light mode. The executing test runs on the `skill tests` seat, which defaults to Claude Haiku 5.5 at high, or at medium under light mode's reasoning cap. A test whose child launches seats resolves that seat with `roles.py show --role "skill tests" --launches-seats`, which never returns a Cursor seat.

## Saving per change

The estimate uses the mean activity items per child from the sample. `how` explainer 19, a 5-seat architect panel 164, one Grok architect runner 54, cross-judge 27, code delegate 53, Comment Sicko 8, gate verifier 38, two `why` investigators 150, the source-control investigator 90, `why` synthesizer 14. A typical change has 1.87 attempts, so 0.87 fix attempts. Every attempt has one gate review.

| Change | Full first attempt | Full fix attempt | Light first attempt | Light fix attempt | Full per change | Light per change |
| --- | --- | --- | --- | --- | --- | --- |
| Feature | 19 + 19 + 164 + 27 + 53 + 8 = 290 | 290 | 19 + 54 + 53 = 126 | 53 | 290 + 0.87 × 290 + 1.87 × 38 = 613 | 126 + 0.87 × 53 + 1.87 × 38 = 243 |
| Bug fix | 19 + 150 + 14 + 53 + 8 = 244 | 244 | 19 + 90 + 53 = 162 | 53 | 244 + 0.87 × 244 + 1.87 × 38 = 527 | 162 + 0.87 × 53 + 1.87 × 38 = 279 |
| Skill change, add | + 10 per attempt | | + 10 per attempt | | + 19 | + 19 |

That is about 60 percent fewer child items for a Feature change and about 47 percent fewer for a Bug fix.

The Bug fix figure depends on the fix-attempt waiver of Why. Without it, a light fix attempt keeps the source-control investigator and costs 143 items. The light total is then 162 + 0.87 × 143 + 1.87 × 38 = 357, about 32 percent below 527.

With the built-in two-seat architect panel (Opus 29 and Grok 54 items), a full Feature change is about 462 items, and light saves about 47 percent. A standalone Feature change in full mode has no gate review, so it costs about 542. Light still saves about 55 percent after adding the gate.

A second set of means checks how much these figures depend on the sample. Across every child in the T3 thread list through 2026-10-07 16:40 UTC, grouped by title, the means are `how` explainer 17, architect runner 30, cross-judge 8.5, code delegate 65, Comment Sicko 10, verifier 40, and `why` investigator 60. Pricing a light runner at two full runners, the saving is about 53 percent for Feature and 45 percent for Bug fix. The cross-judge is the largest difference. The sample's judges ran on panels of five, while most snapshot judges did not.

The worker thread's own items fall too, because it waits on fewer children, and the `medium` cap shortens every seat's reasoning. Neither is in these numbers, since T3 records no tokens. Escalated items run in full and save nothing here. On this repository about half the items escalate, so the measured saving across the whole history is about half of the per-change figure.

Folding the trail reviewer into the gate saves one child per run that keeps a trail. Two historical trail reviews cost 18 and 16 items.

The estimate has three limits. The sample is 10 work items chosen by hand. Activity items are not tokens, and an Opus reasoning block counts as one item however long it runs. Light mode may raise the send-back rate, because fewer design candidates reach the code delegate. A 20 percent rise in fix attempts would take back about 16 items per change.

## Risks

Light mode keeps the round-1 review, and round 1 is where this repository caught most of its real bugs. Of 59 send-backs, 35 rounds held 51 real-bug findings on 24 items. The other 24 rounds held only instruction or doc gaps. Every send-back verdict came from the gating verifier. On D64 the gating verifiers were Grok in round 1 and Space Bunny in round 2. Space Bunny ran as the second reviewer in round 1 and supplied three of that round's findings. In round 2 Grok passed, and Space Bunny, recorded as the gate, found the message-only relay gap. The risks are in what light mode thins around that review.

1. **A weaker verifier.** The reviewer trial shows that a cheaper model misses concurrency bugs. Every trial model passed D59 and D60, which held a mode-overwrite race and three lease failures. Kimi as a second reviewer passed D62 and missed Codex's three crash-safety findings. Light mode therefore keeps the verifier's model and lowers only its reasoning level, and an escalated item keeps the full level. A `medium` cap on the gate is still untested. [Change 6](#change-6-a-measured-light-mode-trial) measures it before light becomes a recommendation.
2. **Later rounds that caught round-1 misses.** D42 round 2 found a duplicate-PR path (`reports/D42-review-2.md`). D55 round 2 found an option-shaped summary that breaks the printed retry (`reports/D55-review-2.md`). D61 round 2 found an unskipped test that fails setup (`reports/D61-review-2.md`). All three are on `land.py` or `brigade.py`, so rule 1 escalates them. Light mode also keeps full-diff re-review.
3. **Fixes that introduce bugs.** D12 rounds 2 and 3 (tag publishing, a second push URL) and D24 rounds 2 to 5 (installer ownership) were bugs the fix itself created. Re-review at every head SHA caught them, and light mode keeps it. D24 is the costliest item in the store, and rule 1 escalates it through `scripts/install.py`.
4. **Second reviewers.** Space Bunny found an empty-path reservation that locks the repository on D61 (`reports/D61-review-space-bunny.md`) and three skill gaps on D64 that Grok missed. Light mode drops second reviewers, so that class of catch is lost. D61 and D64 both changed `brigade.py`, so rule 1 escalates them. The same reviewer stalled or quit on 2 of 6 runs, so it was never a dependable gate.
5. **Skill-text gaps.** 24 send-back rounds held only instruction gaps, such as D11's merge wait that hangs and D64's relay lines that `sync` cannot print. The folded Comment Sicko and the single architect runner touch this class most. The gate review still reads the whole diff, and the executing fresh-child test shows an agent following the text.
6. **The six real-bug items rule 1 misses.** D3 (`measure_capacity.py`), D14 and D25 (`roles.py`), D49 (a concurrency design doc), D50 and D63 (test and shell snippets). Each was caught by its round-1 review, which light mode keeps. A project that wants them in full adds `t3/scripts/roles.py` to `"escalate"`. A design doc about concurrency is a rule-3 case.
7. **The admin relay after this design.** D64's relay gap was caught by a second reviewer that light mode drops. Coverage of the admin relay in light mode is the gate review at `medium`, rule 1 for any change that touches `brigade.py`, and the executing fresh-child test that drives the admin through one relayed reply.

## Changes

Changes 1 to 5 landed in order as #81, #83, #84, #85, and #88. Change 6 is the trial, and [Results](#results) records it.

Each change is one PR through the landing queue, with its own tests and its own changelog fragment. Each change that edits a skill's behavior needs the fresh-child tests [Fresh-child tests in light mode](#fresh-child-tests-in-light-mode) requires, run in `full` mode because the change itself is under review.

### Change 1. The setting

- **What.** `check_shape` accepts `"mode"` (`full` or `light`) and `"escalate"` (a list of pattern strings). `merged_config` merges `mode` like `budget`, project over user, and keeps the project's `escalate` list. `show` prints `mode` and `modeSource`. `write --mode` saves it. `setup-pstack` asks for the mode after the budget and suggests `escalate` patterns for a project.
- **Files.** `t3/scripts/roles.py`, `tests/test_roles_cli.py`, `t3/setup.md`, generated `skills/pstack-runtime/` and `skills/setup-pstack/`, `docs/skills.md`, its fragment.
- **Tests.** A user file with `"mode": "light"` and a project file with `"mode": "full"` make `show` print `"mode": "full"` and the project path as `modeSource`. An unknown mode value exits 1 naming the file. A non-list `escalate` exits 1. A leaf fresh-child test runs setup's mode question.

### Change 2. Effective mode, the cap, escalation, and waivers

- **What.** `effective_mode` implements the precedence. `show` and the new `mode` subcommand share `--brief-mode`, `--session-mode`, and `--coordinator-mode`. `resolve` applies budget `small` under `light` with budget `default`. `mode` takes `--cwd`, `--paths`, `--send-backs`, `--escalated`, `--playbook`, and `--attempt`, applies rules 1 and 2 with the path semantics above, and prints the brief lines. `LIGHT_WAIVERS` holds the waiver table.
- **Files.** `t3/scripts/roles.py`, `tests/test_roles_cli.py`, a new `tests/test_roles_mode.py`, generated `skills/pstack-runtime/`, its fragment.
- **Tests.**
  - `--coordinator-mode light` over a project `full` prints `Mode: light`, and `show` with the same input caps a configured xhigh `verifiers` seat at `medium`.
  - `--brief-mode full` with a project `light` prints `Mode: full`, and `show` leaves the xhigh seat alone.
  - `--session-mode light` over a project `full` gives `light`. `--brief-mode full` over `--session-mode light` gives `full`.
  - Under `light` and budget `default`, an `inherit` seat becomes an explicit target with `medium`. Under `light` and budget `large`, the xhigh seat stays. Under `light` with no `--parent`, `show` prints the `info` line that the cap did not apply.
  - A worktree with a `.git` file and no `.pstack/` resolves `show --brief-mode light` to `light`, although the main checkout's project file says `full`.
  - Path rule, each with a literal expected line. A file lease equal to a pattern escalates. A directory lease `t3/added/landing` escalates on `t3/added/landing/scripts/land.py`. A file lease `t3/added/landing/SKILL.md` does not. The root lease escalates on any tracked match. `**/migrations/**` matches `db/migrations/0001.sql` and not `docs/migrations.md`. `*` does not cross `/`. A `../x` lease exits 1. `./a//b/` normalizes to `a/b`, and `a/../b` to `b`.
  - `--send-backs 2` prints `Mode: full` and `Mode source: escalated: second send-back`. `--escalated "lock order"` prints the same with that reason.
  - `--playbook bug-fix --attempt fix` prints `Waived by mode: How, Why, Architect, Comment Sicko`.

### Change 3. Brief grammar and `check-brief`

- **What.** `check-brief` enforces [the rules above](#rolespy-check-brief) on the lines a brief carries. It does not yet require `Mode:`, because no producer writes it until Change 4. A brief without `Mode:` checks as it does today. The runtime's Delegation step 4 names the `Mode:` line and the copy-into-`--brief-mode` rule. The runtime's Roles section updates its `roles.py show` command recipes (`t3/runtime.md:94`, `:102`) as well as its prose. Each recipe passes `--brief-mode <value>` when the brief has a `Mode:` line, and `--session-mode light` in a light session. A call with neither flag resolves as it does today, so existing callers keep working between landed changes.
- **Files.** `t3/scripts/roles.py`, `t3/runtime.md`, `tests/test_roles_cli.py`, generated `skills/pstack-runtime/`, `docs/skills.md`, its fragment.
- **Tests.** A brief with the persona, `Playbook: playbooks/feature.md`, `Mode: light`, `Attempt: first`, and `Waived by mode: Arena, Interrogate, Comment Sicko` passes. Two `Mode:` lines fail with `more than one Mode line: keep one`. `Mode: light (from restaurant.json)` fails and names the two values. `Waived by mode: How` under `Mode: full` fails. `Waived by mode: How` on a first-attempt Feature fails and prints the expected list. A light brief with no `Attempt:` fails. A code delegate brief with no `Mode:` still passes, as today. `roles.py show` with no mode flag prints the same seats it prints today.

### Change 4. The runtime's Modes section and the workflow rules

- **What.** `t3/runtime.md` gains a `## Modes` section with the precedence, the light table, the never-cut list, the gate review and its reuse rule, and the announcement. The Deadlines paragraph gains one sentence. It says a step that the brief's `Waived by mode:` line names is not a skip. Each skill that spawns gains one sentence that points at the section for its light behavior. Opening a PR gains the gate step, with reuse from source 2 only. Source 1 arrives with Change 5. `check-brief` starts to require `Mode:` in a code delegate's brief in this change, the same change that teaches every producer to write it (the runtime's Delegation step 4, the code-writing playbooks, `arena`, and `swarm`). `scripts/check.py` gains a rule that fails when a skill restates the light table instead of linking it.
- **Files.** `t3/runtime.md`. `t3/overrides/poteto-mode/SKILL.md`. Playbooks `feature.md`, `bug-fix.md`, `refactoring.md`, `perf-issue.md`, `hillclimb.md`, `opening-a-pr.md`, `autopilot-full.md`, `autopilot-stack.md`, `multi-phase-plan.md`, `orchestrate.md`, `shipping.md`, `visual-parity.md`, `worktree-cleanup.md`. Overrides `how`, `why`, `architect`, `arena`, `no-comments`, `swarm`, `interrogate`, `show-me-your-work`, `recall`, `automate-me`, `maintain-verification-skill`, `reflect`. `t3/added/pstack-author-skill/SKILL.md`. `t3/added/landing/SKILL.md`. `scripts/check.py`, `tests/test_pstack_t3.py`. `t3/overrides.lock.json` only after review. Generated `skills/`, `docs/skills.md`, its fragment.
- **Tests.** `tests/test_pstack_t3.py` feeds `check.check_tree` a skill that pastes the waiver table and expects the failure line, and one that links the section and expects a pass. Executing fresh-child tests, one per changed spawn behavior:
  1. A standalone light Feature request outside brigade. It spawns one `how` explainer, one architect runner, and one code delegate, no Comment Sicko child, and one gate review on another family. It writes the `Gate:` line into a PR body draft and stops before opening the PR.
  2. The same request in full mode still runs the panel, the judge, and Comment Sicko.
  3. A light Bug fix fix attempt with a findings file. It reproduces the finding, spawns no `how` or `why`, and runs the code delegate.
  4. A light Autopilot-stack root rebases a PR whose patch-id is unchanged. It reuses the PR's test lane under the patch-id rule, launches a new gate review at the new head SHA, and cites that gate in the PR body.
  5. A light run with a decision trail. The gate review flags a seeded skipped verification, and no separate trail reviewer runs.
  6. Light `maintain-verification-skill` over five feature files spawns at most three source children.
- The six tests above are the floor. Each workflow edit in this change adds its own executing test, one per changed spawn or coordination behavior. That includes the Autopilot, Orchestrate, and visual-parity owners' `Mode:` briefs, the recall slice cap, the parent-written `why` synthesis, the multi-phase and Autopilot verification lanes, and Shipping's gate reuse.
- Leaf tests cover the reply's mode announcement and the `$poteto-mode light` trigger.

### Change 5. brigade's mode

- **What.** `brigade.py open --mode` and `set --mode` record `mode` in `restaurant.json`, and `set --mode ""` removes it. `fire --mode full --reason` and a new `dish <item> --mode full --reason` flag append the item's `mode` row to `log.tsv` under the store lock and the owner fence. A `dish --mode light` is refused. `dishes.tsv` gains no mode column, so the `log.tsv` row stays the only record. `brief` counts send-backs from `pass.tsv`, reads the item's latest `mode` row in `log.tsv`, and calls `roles.py mode` with the coordinator mode, `--escalated "<reason>"` when that row exists, the lease paths, the playbook, and the attempt kind, writes the printed lines, and persists the first escalation. `brief`'s REPORT section gains a `Contested:` line. The Review step handles `Contested:` before it marks the report ready for a gate. It stops the old worker, records the escalation with `dish --mode full`, and launches a fresh full worker with the report, keeping the item's lease through the replacement. A contested report is not a send-back, writes no `pass.tsv` row, and does not count toward rule 2. `status` and `walk` print the mode. Coordinator `report` adds a `mode` entry to its `SECTIONS` map (`brigade.py:56`), so a digest shows each escalation. `pass check --json` prints the latest row for the item and SHA, selected by `pass_check`'s code, with `verdict`, `author`, `verifier`, `note`, and `crossFamily`. It exits as `pass check` does. The runtime's Modes section and Opening a PR add gate reuse source 1, which uses it. The skill's Open step asks for the mode. The Review step compares skips with the waived line and runs the gate brief with the folded checks. The send-back step writes the fix-attempt brief. Light mode drops the weekly reflect. A usage limit parks the mode choice with `86 add`. The menu template's `## Budget` line drops the roles budget and keeps the worker cap.
- **Files.** `t3/added/brigade/scripts/brigade.py`, `t3/added/brigade/SKILL.md`, `t3/runtime.md`, `t3/overrides/poteto-mode/playbooks/opening-a-pr.md`, `tests/test_brigade.py`, `t3/overrides.lock.json` only after review, generated `skills/brigade/`, `skills/pstack-runtime/`, `skills/poteto-mode/`, `docs/skills.md`, its fragment.
- **Tests.** `open --mode light` writes `"mode": "light"`. A first-attempt Feature brief under light prints `Mode: light`, `Attempt: first`, and `Waived by mode: Arena, Interrogate, Comment Sicko`. After one `send-back` row, `brief` prints `Attempt: fix` and the fix waivers. A replacement worker with no new `send-back` row does not count as a send-back. After two `send-back` rows, `brief` prints `Mode: full` and appends one `mode` row to `log.tsv`. A second `brief` appends no duplicate. After that, `set --mode light` leaves the next brief at `Mode: full`. `dish --mode full` with a stale `--owner` exits 1 and appends nothing. `dish --mode light` exits 1. `set --mode light` while an item is in progress leaves its written brief unchanged. A store replayed from its `log.tsv` keeps the escalation, and a write with a stale `--owner` changes no earlier row. `pass check --json` on a cross-family pass prints `"crossFamily": true` and exits 0. A pass followed by a `send-back` at the same SHA exits 1 and prints `"verdict": "send-back"`. A pass recorded with `--same-family` prints `"crossFamily": false`. A pass recorded at one SHA and checked at another exits 1 with `has no review verdict`. Executing fresh-child tests drive a coordinator through one light item to its gate, and drive a standalone light Feature whose head has a current cross-family brigade pass. That Feature launches no second gate and cites the pass. The same Feature, after a send-back is recorded at that SHA, launches a gate. Another executing test drives one worker report that says `Contested:`. That test shows the old worker stopped, one `mode` row with state `full`, a fresh worker on a full seat with `Mode: full` in its brief, the lease unchanged through the replacement, and no new `send-back` row.

### Change 6. A measured light-mode trial

- **What.** Run the next six work items of one coordinator in light mode and six comparable ones in full. Compare child activity items per item, send-backs per item, and real-bug findings per round, with the commands in [Appendix A](#appendix-a-commands). During the trial, every light item's gate runs twice at each reviewed head SHA, once at `medium` and once at the full level. That includes every pre-fix SHA, so a bug the `medium` gate missed on an earlier head still shows even after the worker removes it.
- **Gate during the trial.** The item lands only when both reviews pass at its final head. A blocking finding from the full-level review is a send-back at that SHA, whatever the `medium` review said, and counts as a `medium` miss.
- **Files.** `docs/light-mode.md` gains a Results section. No code.
- **Decision.** The gate keeps the `medium` cap only if the full-level reviews found no blocking finding that the `medium` reviews missed on any evaluated SHA. Otherwise the gate keeps its full level in light mode, and only the worker-side cuts remain. Light mode becomes the recommended choice under a usage limit after that decision.
- **Outcome.** The full-level reviews found a blocking finding the `medium` reviews missed on 3 of 8 evaluated commits. The gate keeps its full level in light mode. See [Results](#results).

## Results

The trial ran 12 work items through one coordinator on 2026-10-09 and 2026-10-10, six in light mode and six in full mode as controls. It asked the question [Change 6](#change-6-a-measured-light-mode-trial) states. Does a `medium` gate review miss a blocking finding that a full-level review reports at the same commit? It did, at 3 of the 8 commits where both reviews ran. The gate therefore keeps its full level in light mode. The cost side of the design is unmeasured.

### Trial method

- **Assignment.** The items alternated. The light items are D97, D99, D101, D104, D106, and D108. The controls are D98, D100, D102, D105, D107, and D109. Each control carries a `mode` row in `log.tsv` with the reason `light-mode trial control`. No light item carries one, and each light brief says `Mode source: restaurant.json`.
- **Paired gate reviews.** At each reviewed head of a light item, one read-only brief ran twice, once at the `medium` level and once at the full level. `pass.tsv` names `codex/gpt-6.1-sol` as the verifier at each of those heads. A numbered blocker in the full review that the `medium` review did not report is a medium miss, as [Change 6](#change-6-a-measured-light-mode-trial) defines it.
- **Controls.** A control ran one review per head at the full level. It gives send-backs and findings and no comparison.
- **Free panel.** When Codex was at its usage limit, the `review backups` seats ran in its place. They are three free OpenCode reviewers, Muse, Step 5, and Space Bunny. A panel pass is 3 of 3 passes.
- **Verification.** For each of the 8 paired heads, the `medium` and full review files were read side by side and every blocker was matched to its counterpart. The counts below come from that reading. The trial table's note that medium found 5 of the 7 blockers at D108 round 1 is one short. The `medium` review's five blockers cover six of the full review's seven, because its first blocker folds two.
- **Unit.** A finding is a numbered blocker. A reviewer can fold several defects into one entry, so counts compare reviewers only roughly.

### Trial table

| Item | Playbook | Mode | Send-backs | Blocking findings by round | Medium misses | Reviewer at each round |
| --- | --- | --- | --- | --- | --- | --- |
| D97 installer holder recovery | Bug fix | light | 0 | 0 | not measured | free panel, 3 of 3 pass |
| D98 install docs after D92 | Refactoring | full | 3 | 4, 2, 2, 0 | n/a | Codex |
| D99 no queue line in PR bodies | Bug fix | light | 0 | medium 0, full 0 | 0 | Codex at both levels |
| D100 `scripts/release.py` | Feature | full | 2 | 2, 2, 0 | n/a | Codex |
| D101 record every round, round budget | Feature | light | 2 | medium 3, 1, 0 and full 4, 2, 0 | 2 (rounds 1 and 2) | Codex at both levels |
| D102 docs batch after D95 to D99 | Refactoring | full | 0 | 0 | n/a | free panel, 3 of 3 pass |
| D104 remove the `Q<n>` alias | Refactoring | light | 2 | medium 2, 1, 0 and full 2, 1, 0 | 0 | Codex at both levels |
| D105 installer follow-ups | Bug fix | full | 0 | 0 | n/a | Codex |
| D106 generated CLI reference | Feature | light | 0 | 0 | not measured | free panel, 3 of 3 pass |
| D107 `sync_upstream.py --check` | Feature | full | 0 | 0 | n/a | free panel, 3 of 3 pass |
| D108 landing skill states each rule once | Refactoring | light | 1 | round 1 medium 5 and full 7, round 2 0 | 1 (round 1) | round 1 Codex at both levels, round 2 free panel, 3 of 3 pass |
| D109 0.3.0 changelog | Refactoring | full | 1 | 4, 1 | n/a | round 1 Codex, round 2 free panel, 2 of 3 pass |

The six light items had 5 send-backs and the six controls had 6. The twelve items change different things, so those counts say nothing about the mode. D109 round 2 counts one finding that sits in the owner notes outside the commit.

### The paired reviews

| Item | Round | Head | Medium | Full | Medium miss |
| --- | --- | --- | --- | --- | --- |
| D99 | 1 | `0486ebb` | pass | pass | none |
| D101 | 1 | `a1e9a27` | fail, 3 | fail, 4 | a mid-sentence colon in new skill prose |
| D101 | 2 | `e34bcb7` | fail, 1 | fail, 2 | `watch` hid an owed decision on a dropped or merged item |
| D101 | 3 | `a9ee4f2` | pass | pass | none |
| D104 | 1 | `0641090` | fail, 2 | fail, 2 | none |
| D104 | 2 | `ad69aaf` | fail, 1 | fail, 1 | none |
| D104 | 3 | `3d95e19` | pass | pass | none |
| D108 | 1 | `c6394ce` | fail, 5 | fail, 7 | the condition on pushing a replacement pull request's branch |

The three misses are these.

1. **D101 round 1.** The full review's fourth blocker is the new line `Decision pending: when ...` in `t3/added/brigade/SKILL.md`, which breaks the mid-sentence colon rule, and the test that pins it. The `medium` review wrote that it found no prose-style blocker. This miss is style only. The worker removed the colon in round 2.
2. **D101 round 2.** The full review's first blocker is that `watch` printed `no work in progress` for a dropped or merged item that still owed its round decision, while restarting it and firing its ticket stayed refused. The `medium` review reported only the prose promises that overstated the code, and it stated that `watch` shows the pending line in every open state. This miss is a behavior defect under the round 2 rule. Round 3 narrowed the rule so that only an open item owes a decision, which removed the case.
3. **D108 round 1.** The full review's third blocker is that the new lifecycle text kept the unconditional sentence that `land` pushes the checked candidate to `landing/e<n>` and opens a new pull request. `ensure_pr` calls `publish_absent_branch`, which pushes only when the branch is absent. The same review's first blocker also flags the stale `status Q<n>` sentence at line 91, which the `medium` review did not name. This miss is a sentence the code contradicts, which the review brief counts as a failure. The worker covered both in the same fix round without having read the full review.

The pairs agree on pass or fail at 8 of 8 heads. A `medium`-only gate would have failed the same five heads and passed the same three. It would have handed back 12 blockers where the full level handed back 16, which is 3 misses and 1 fold. The `medium` review also reported two things the full review did not. At D101 round 2 it found that `brief` on a passed item prints the passed-state error and not the promised budget diagnostic. At D108 round 1 it found mid-sentence colons at lines 67 and 78 that the full review left out.

### Decision

The design states the rule in [Change 6](#change-6-a-measured-light-mode-trial).

> The gate keeps the `medium` cap only if the full-level reviews found no blocking finding that the `medium` reviews missed on any evaluated SHA. Otherwise the gate keeps its full level in light mode, and only the worker-side cuts remain. Light mode becomes the recommended choice under a usage limit after that decision.

The rule asks for no miss on any evaluated commit. Three of the eight commits have one, on two of the four items that have a paired comparison. The first clause fails, so the second applies. **The gate review keeps its full level in light mode.**

Two facts show the decision does not hang on one reading of the data.

- Two of the three misses are not style. D101 round 2 is a behavior defect and D108 round 1 is a false statement in skill text.
- The result does not depend on the path rule. No `escalate` list was configured, so seven of the eight paired heads, on `land.py` and `brigade.py`, ran light where the design's list would have made them full. D108 round 1 changed only skill prose, so it would have stayed light under that list, and it has a miss.

What follows from the decision.

- **The worker-side cuts remain.** These are the single architect runner, the simple `how` path, the source-control-only `why`, the folded Comment Sicko, the waivers, the fan-out cap of 3, and the reasoning cap on every seat that is not the gate.
- **The code and skills still cap the gate.** Under light mode with budget `default`, `roles.py show` resolves the `verifiers` seat at `medium`, and the runtime's Modes section and the Summary table above say so. A follow-up change must leave the `verifiers` seat at its configured level when it resolves a gate review, with a test that a configured `high` gate stays `high` under light, and must correct those passages. This document does not make that change.
- **Light mode becomes the recommended choice under a usage limit.** That is the rule's last sentence. The trial supports the gate half of it. The saving the recommendation rests on is the design's estimate, which the trial did not test.
- **The saving estimate does not change.** [Saving per change](#saving-per-change) counted no reasoning saving, so a gate at full level leaves its figures as they were.

### What the trial did not measure

- **Cost.** Child activity counts were not collected for any of the 12 items, so the trial says nothing about the 45 to 60 percent estimate. A measurement needs, for each item, the sum of `itemCount` from `t3_thread_read` over the worker thread and every child task it launched, across all attempts, and the same sum for each gate review at each level. It also needs matched pairs of comparable size in the same playbook. T3 records no tokens or reasoning level, so the unit stays activity items and a reasoning cap's saving stays invisible. The counts for these 12 items can be taken after the fact only if T3 still holds their threads.
- **The comparison on most items.** Paired reviews exist for 4 items and 8 heads. D97 and D106 are light items reviewed only by the free panel, because Codex was at its usage limit, so they give no comparison. D108 round 2 ran on the panel too, and D108 landed on that pass and not on the two Codex passes the protocol asks for.
- **Run-to-run variance.** Each head had one review per level. No level ran twice, so a difference between two reviews may come from the run and not from the level. The two things the `medium` review reported alone are the evidence that variance is not zero.
- **The review level.** The review files do not record the reasoning level. It comes from the file names and the `pass.tsv` notes, and T3 holds none.
- **Matched work.** The 12 items are not matched pairs. The playbook mix is close, with two bug fixes, two features, and two refactorings among the light items against one, two, and three among the controls, but the changes differ.
- **Escalation.** No `escalate` list was configured, so rule 1 never fired. D101 and D104 each reached two send-backs while light, and `log.tsv` holds no `mode` row for either, so rule 2 did not fire. Four of the six light items changed `install.py`, `land.py`, or `brigade.py`, which the design's list would have escalated. The trial measures the gate cap and the worker-side cuts, and not light mode as the design escalates it.

### What the trial showed outside its question

- **Prose items drew more send-backs than code items.** D98, D102, D108, and D109 changed prose and had 3, 0, 1, and 1 send-backs, 5 in 4 items. The eight code items had 6. D102 is the one prose item with no send-back, and only the free panel reviewed it.
- **A prose send-back was a false statement checked against code.** D98 held 8 false or too-broad statements across rounds 1 to 3. D108 round 1 and D109 round 1 held stale or false lines. No prose send-back was style alone.
- **Six of the 11 send-backs held a behavior bug with a reproducing command.** They are D100 rounds 1 and 2, D101 rounds 1 and 2, and D104 rounds 1 and 2. The other five held only false or stale statements.
- **A fix round seeded the next round's finding in three items.** D100 round 2 found signal windows in the rollback that round 1 added. D101 round 2 found the debt rule applied to terminal items after round 1 widened the guards. D104 round 2 found a hidden branch treated as gone in the settlement fallback that round 1 added. The next round's review caught all three.
- **Half of the items landed on the free panel.** D97, D102, D106, D107, D108, and D109 passed their final head there because Codex was at its limit. The panel passed 3 of 3 on five heads and 2 of 3 on D109, where one member's only blocker was a false line in the owner notes outside the commit.
- **The panel's non-blocking notes held real defects.** It passed D97 with notes that became ticket T142 and then D105. D105 fixed a holder sweep that ignored `--harness`, an install that exited on a conflict without a `left` line, and a state directory created for a run that found only unproven entries. Four items had no reviewer other than the panel, so the trial cannot say what it missed on them.
- **A thorough worker closed a miss without reading the full review.** At D108 the worker fixed from the `medium` review only, and its rewrite of the section against the code also covered the full review's two extra findings. A miss that the next fix round absorbs still counts, since the gate cannot rely on a worker's diligence.

## Out of scope

- Changing which model family gates review. The trial evidence says the current gate is the strongest available, and light mode does not move it.
- An automatic switch on a usage limit. T3 reports a limit only as a failed child. The coordinator parks the choice for the user instead.
- A mode per playbook step. One switch with one table is easier to reason about than a matrix, and escalation covers the cases that need more.
- Narrower leases for skill text. Rule 1 fires on the scripts items actually change, as [Escalation](#escalation) shows.
- Coordinator wake frequency. At `digest` the liveness schedule already runs every 30 minutes, and the coordinator's own runs are a standing cost this design does not measure per item.

## Appendix A. Commands

Save the three scripts below as `history.py`, `squash.py`, and `durations.py` in a scratch directory outside the repository, then run these from the repository root with that directory's path. `S` is the store and `R` the real-bug item list from Appendix B.

```bash
S=~/.local/state/pstack-t3/brigade/pstack-t3/pstack-t3
R=D2,D3,D4,D6,D12,D14,D17,D24,D25,D27,D42,D47,D49,D50,D52,D53,D55,D56,D59,D60,D61,D62,D63,D69
grep -rnE "delegate_task|t3_thread_launch|create_threads" t3 --include=*.md
python3 -I history.py "$S" "$PWD" "t3/added/landing/scripts/land.py,t3/added/brigade/scripts/brigade.py,scripts/install.py" "$R" D72
python3 -I squash.py "$S" "$PWD" "t3/added/landing/scripts/land.py,t3/added/brigade/scripts/brigade.py,scripts/install.py" D72
```

`history.py` prints the verdict counts, the attempt histogram, and the rule 1 and rule 2 results. It implements the path semantics in [Escalation](#escalation).

```python
import csv, collections, fnmatch, posixpath, statistics, subprocess, sys

store, repo, through = sys.argv[1], sys.argv[2], int(sys.argv[5].lstrip("D"))
patterns = sys.argv[3].split(",")
real = set(sys.argv[4].split(","))
dishes = list(csv.DictReader(open(f"{store}/dishes.tsv"), delimiter="\t"))
merged = {d["id"]: d for d in dishes if d["state"] == "merged" and int(d["id"][1:]) <= through}
verdicts = [p for p in csv.DictReader(open(f"{store}/pass.tsv"), delimiter="\t") if p["dish"] in merged]
rounds = collections.Counter(p["dish"] for p in verdicts)
sendbacks = collections.Counter(p["dish"] for p in verdicts if p["verdict"] == "send-back")
print("merged", len(merged), "verdicts", len(verdicts), "send-backs", sum(sendbacks.values()))
print("rounds histogram", sorted(collections.Counter(rounds[i] for i in merged).items()),
      "mean %.2f" % statistics.mean(rounds[i] for i in merged))

def normalize(path):
    canonical = posixpath.normpath(path.strip().replace("\\", "/")).lstrip("/")
    if canonical in (".", ""):
        return []
    if canonical == ".." or canonical.startswith("../"):
        raise ValueError(f"lease path leaves the repository: {path}")
    return canonical.split("/")

def match(segs, pats):
    if not segs:
        return all(p == "**" for p in pats)
    if not pats:
        return False
    if pats[0] == "**":
        return match(segs, pats[1:]) or match(segs[1:], pats)
    return fnmatch.fnmatchcase(segs[0], pats[0]) and match(segs[1:], pats[1:])

tracked = subprocess.run(["git", "-C", repo, "ls-files"], capture_output=True, text=True, check=True).stdout.split()

def covered(lease):
    segs = normalize(lease)
    under = [f for f in tracked if f.split("/")[:len(segs)] == segs and len(f.split("/")) > len(segs)]
    return [segs] + [normalize(f) for f in under]

def escalates(lease):
    return any(match(segs, normalize(p)) for segs in covered(lease) for p in patterns)

esc = {i for i, d in merged.items() if any(escalates(p) for p in d["paths"].split(",") if p)}
key = lambda x: int(x[1:])
print("rule 1 escalates", len(esc), "items carrying", sum(sendbacks[i] for i in esc), "send-backs")
print("real-bug items escalated", len(esc & real), "of", len(real), "missed", sorted(real - esc, key=key))
print("rule 2 adds at attempt 3", sorted((i for i in merged if i not in esc and sendbacks[i] >= 2), key=key))
```

Its output at the snapshot:

```text
merged 69 verdicts 129 send-backs 59
rounds histogram [(1, 25), (2, 33), (3, 8), (4, 2), (6, 1)] mean 1.87
rule 1 escalates 34 items carrying 35 send-backs
real-bug items escalated 18 of 24 missed ['D3', 'D14', 'D25', 'D49', 'D50', 'D63']
rule 2 adds at attempt 3 ['D16', 'D23', 'D25', 'D49', 'D63']
```

`squash.py` lists the merged items whose squash commit on `main` touched a risk file.

```python
import csv, re, subprocess, sys

store, repo, through = sys.argv[1], sys.argv[2], int(sys.argv[4].lstrip("D"))
risk = set(sys.argv[3].split(","))
log = subprocess.run(["git", "-C", repo, "log", "--format=%H %s", "main"], capture_output=True, text=True, check=True).stdout
pr2sha = {m.group(2): m.group(1) for m in re.finditer(r"^(\w+) .*\(#(\d+)\)$", log, re.M)}
rows = [d for d in csv.DictReader(open(f"{store}/dishes.tsv"), delimiter="\t")
        if d["state"] == "merged" and int(d["id"][1:]) <= through]
hit = []
for d in rows:
    sha = pr2sha[d["pr"].rsplit("/", 1)[-1]]
    files = subprocess.run(["git", "-C", repo, "show", "--name-only", "--format=", sha],
                           capture_output=True, text=True, check=True).stdout.split()
    if risk & set(files):
        hit.append(d["id"])
print(len(hit), hit)
```

It prints 32 items. The rule 1 set minus that list is D5 and D11.

`durations.py` computes the durations from `log.tsv` rows of kind `dish`. A worker run is each `in-progress` to the next `in-review`. A review is each `in-review` to the next `passed`, `sent-back`, or `blocked`. An item runs from its first `in-progress` to its last `merged`. p90 is the value at index `int(0.9 × n)` of the sorted list. Run it as `python3 -I durations.py "$S" D72`.

```python
import collections, csv, statistics, sys
from datetime import datetime

store, through = sys.argv[1], int(sys.argv[2].lstrip("D"))
events = collections.defaultdict(list)
for r in csv.DictReader(open(f"{store}/log.tsv"), delimiter="\t"):
    if r["kind"] == "dish" and int(r["id"][1:]) <= through:
        events[r["id"]].append((datetime.fromisoformat(r["at"]), r["state"]))
work, review, total = [], [], []
for rows in events.values():
    if not any(s == "merged" for _, s in rows):
        continue
    total.append(([t for t, s in rows if s == "merged"][-1] - rows[0][0]).total_seconds() / 60)
    started = submitted = None
    for t, s in rows:
        if s == "in-progress":
            started = t
        elif s == "in-review":
            if started:
                work.append((t - started).total_seconds() / 60)
            started, submitted = None, t
        elif s in ("passed", "sent-back", "blocked") and submitted:
            review.append((t - submitted).total_seconds() / 60)
            submitted = None
for name, xs in (("worker run", work), ("review", review), ("item", total)):
    xs = sorted(xs)
    print(name, "n", len(xs), "median %.1f mean %.1f p90 %.1f" % (statistics.median(xs), statistics.mean(xs), xs[int(len(xs) * 0.9)]))
```

Its output at the snapshot:

```text
worker run n 129 median 12.8 mean 17.8 p90 30.7
review n 129 median 5.2 mean 6.6 p90 11.2
item n 69 median 41.9 mean 56.8 p90 118.5
```

## Appendix B. Send-back classification

A real bug is wrong behavior in code, a script, or a design mechanism. That covers a bad merge, a lost or corrupt record, a race, a stuck queue, a lock held across a wait, a broken invariant, or a test gate that fails. An instruction or doc gap is skill text, a playbook, the guide, or a changelog that tells an agent or a reader the wrong thing. The report files are under `reports/` in the store.

Real-bug rounds, 35 on 24 items, 51 findings:

| Item | Rounds | Reports |
| --- | --- | --- |
| D2, D3, D4, D6 | 1 each | `D<n>-review.md` |
| D12 | 3 | `D12-review.md`, `-2.md`, `-3.md` |
| D14, D17, D27, D47 | 1 each | `D<n>-review.md` |
| D24 | 5 | `D24-review.md`, `-2.md` to `-5.md` |
| D25 | 1 | `D25-review.md`, findings A and B |
| D42 | 2 | `D42-review.md`, `-2.md` |
| D49 | 2 | `D49-review.md` R2 and R3, `D49-review-2.md` |
| D50, D52, D53, D56, D59, D60, D62, D69 | 1 each | `D<n>-review-1.md` |
| D55, D61, D63 | 2 each | `D<n>-review-1.md`, `-2.md` |

Rounds with instruction or doc findings, 28, holding 45 findings. D11, D13, D16 (2), D18, D19, D23 (2), D25 (finding C, and round 2 finding D), D26, D28, D31, D33, D40, D41, D43, D48, D49 (R1), D57, D63 (round 1 finding 4), D64 (2), D65, D69 (finding 2), D70, D71, D72.

D25 round 1, D49 round 1, D63 round 1, and D69 round 1 held both kinds, so they count in both lists. The other 24 rounds held only instruction or doc findings, and 35 plus 24 is the 59 send-backs. D25 round 2 holds only finding D, an instruction gap. The classification came from one reader. The review of this design spot-checked D14, D25, D49, and D61 against their reports.

## Appendix C. Sampled child activity

The sample is 10 work items chosen by hand to span Feature, Bug fix, skill text, and docs, weighted to D50 and later. It holds D1, D8, D24, D50, D51, D64, D65, D70, D71, and D72. For each item, every attempt's worker thread was read with `t3_thread_read`, and each child's `itemCount` was summed by role from its title. The latest worker thread is the `thread` column of `dishes.tsv`. Earlier attempts are found with `t3_thread_search` on the item id.

D1's first attempt reproduces from live activity. Its `how` child has 29 items. The five runners have 80, 29, 17, 44, and 28, and the judge has 29, so the panel and judge total 227. The code child has 51, for 307 in all. D70's executing Architect-parent test has 111.

The per-child means come from this sample. The second set of means in [Saving per change](#saving-per-change) groups every child in the T3 thread list through 2026-10-07 16:40 UTC by title prefix. It counts 20 `how` explainers, 45 architect runners, 2 cross-judges, 21 code delegates, 11 Comment Sicko runs, 152 verifiers, 10 `why` investigators, and 2 trail reviews.
