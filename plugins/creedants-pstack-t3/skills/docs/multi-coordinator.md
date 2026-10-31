# Several coordinators on one repository

This is the design for running two or more brigade coordinators on one repository, each with its own purpose, so that they share leases, the landing queue, and intake without duplicating work or blocking each other. The intended reader is the user who opens a second coordinator on a repository that already has one, and the engineer who builds the changes below.

In this document a coordinator is one standing coordinator thread and its store directory, and a work item is one unit of work handed to a worker. brigade's commands and files use kitchen names, and this document keeps those names only for commands and files, such as `fire`, `ticket add`, `dishes.tsv`, and `restaurant.json`. Two coordinators are siblings when their `restaurant.json` files name the same `projectRoot`.

## Summary

| # | Gap | What happens today | Change |
| --- | --- | --- | --- |
| 1 | Duplicate intake | `ticket add` accepts the same `--ref` in two coordinators, and twice in one | 4 |
| 2 | No cap across coordinators | `fire` enforces no cap at all, not even the standing-orders cap of one coordinator | 2, 5 |
| 3 | No handoff | No command moves a ticket to a sibling | 4 |
| 4 | Overlapping purposes | `open` prints only the directory and says nothing about siblings | 3 |
| 5 | Blocked tickets go dark | A refused `fire` records nothing. No command shows the blocking lease or notices that it freed | 5 |
| 6 | Mode drift | `set --landing` changes only its own `restaurant.json`. `land.py mode` changes every coordinator's mode, and siblings keep a stale value | 7 |
| 7 | Hot shared files | 17 of 49 work items leased `CHANGELOG.md`, `README.md`, or `docs/guide.md` | 1, 3 |
| 8 | No combined view | `walk` lists coordinators flat, with stale modes and no queue or lease state | 7 |
| 9 | Work landed by a sibling | A sibling's `land` run settles your entry. Your next `land` prints `nothing to land`, and brigade never recorded the entry id | 2, 6 |
| 10 | Lease expiry | `fire` claims a 6-hour lease and nothing renews it. After expiry a sibling can claim the same paths, and the holder's `submit` fails | 2, 6 |
| 11 | Store collision | Two repositories with the same directory name share a store directory. `open` returns the other repository's coordinator | 3 |
| 12 | Renew breaks the lease invariant | `lease renew` revives an expired lease after a sibling claimed the same paths, leaving two active leases on one file | 2 |

Gaps 1 to 8 were known before this audit. Gaps 9 to 12 are new. Changes 1 to 11 are listed in landing order under [Changes](#changes). Changes 1 to 7 close every gap without a new role, and they are built and tested in a [live two-coordinator run](#live-two-coordinator-run) before any admin work starts. Changes 8 to 10 then add the optional [executive admin](#the-executive-admin) the user asked for, for one repository. It keeps the user up to date across every coordinator on that repository. It settles conflicts between them by published rules, and logs every ruling for the user to review and overrule.

## Method

Two sources fed the audit.

1. The code in `t3/added/brigade/scripts/brigade.py`, `t3/added/landing/scripts/land.py`, both `SKILL.md` files, and `docs/guide.md`.
2. A scratch experiment, rerunnable from the [experiment script](#the-experiment-script) at the end of this document. It creates a repository under `mktemp -d` with a local bare origin, sets `XDG_STATE_HOME` and `BRIGADE_STORE` to scratch directories, runs `land.py init --mode push --check true`, and opens coordinators `docs` and `engine` on it with the generated `skills/` scripts. It then adds tickets with the same `--ref`, starts overlapping work, submits and lands from one coordinator, changes the mode from one, lets a lease expire, and runs `walk`. The real stores under `~/.local/state` were only read, never written.

The numbers about real use come from the pstack-t3 coordinator's store (`dishes.tsv`, `log.tsv`) and its landing database (`land.db`, opened read-only). They cover 49 work items and 50 leases over the 40 hours between the first lease claim and the last release.

## What happens today

### 1. Duplicate intake

Observed. `ticket add --ref https://github.com/o/r/issues/7` returned `T1` in `docs` and `T1` in `engine`. A second add of the same ref in `engine` returned `T2`. `ticket add` checks no ref, in its own `rail.tsv` or a sibling's. Two coordinators whose standing orders both name `gh issue list` as an intake source therefore each file every issue, and each starts its own work for it.

### 2. No cap across coordinators

Observed. `engine` started four work items in a row with no refusal while `docs` held a fifth. The cap in pstack-t3's `menu.md` and standing orders ("at most 3 workers in flight") is prose. `fire` reads neither, so there is no enforced cap per coordinator, per repository, or per machine. The governor (`land.py slot`) already caps builds and tests machine-wide. Agent threads have no cap.

### 3. No handoff

Observed. `ticket move` exits 2 with `invalid choice: 'move'`. Today a coordinator can only drop the ticket and ask the user, or message the sibling's thread and hope it files the ticket. The original ticket keeps no record of where the work went.

### 4. Overlapping purposes

Observed. A third `open` on the same project root printed `opened $T/brigade/app/release` and nothing else. The opening steps in the skill draft `menu.md` from the README, issues, and threads, and never from the siblings' `menu.md` files.

### 5. Blocked tickets go dark

Observed. `engine`'s `fire --paths src/a.py,CHANGELOG.md` failed with `nothing fired: paths overlap L1 held by docs/D1 on CHANGELOG.md, docs/guide.md`. The ticket stayed `waiting`, `status` printed `waiting tickets: 2`, and `log.tsv` gained no row. `land.py` logs no refused claim either. The skill says to leave such tickets waiting until the lease is released. Nothing tells the coordinator when that happens. `watch` reports only work in progress, and the liveness schedule is deleted when `watch` prints `no work in progress`, so a coordinator whose only work is a blocked ticket wakes again only on intake, the morning service, or the evening report.

### 6. Mode drift

The known description of this gap, that `set --landing` changes the mode for every coordinator, is half right. `set --landing merge` in `docs` changed only `docs/restaurant.json`. `land.py status` still said `push mode`, and `engine` still recorded `push`. The repository's mode changes only through `land.py mode`, and that change does reach every coordinator. `land.py mode human` succeeded with no output about who else was affected, and both `restaurant.json` files kept their old values. `land.py mode` does refuse while any entry is queued (`1 entries are queued, landing, or awaiting merge`), so a mode change never strands a sibling's queued work.

The real defect is two sources of truth. `walk` printed `lands by merge` for `docs` and `lands by push` for `engine` while the contract said `push`. pstack-t3's own standing orders restate the mode too, so a sibling's `land.py mode` makes every brief it pastes wrong.

### 7. Hot shared files

Measured from the real stores. 17 of the 49 work items leased at least one of `CHANGELOG.md`, `README.md`, and `docs/guide.md`. Counted as leases on the exact path, `docs/guide.md` had 12, `README.md` 10, and `CHANGELOG.md` 9, which puts them among the most leased paths in the repository. The 12 leases on `docs/guide.md` belong to 11 work items, because D42 held two of them, L42 and L46. Leases holding one of the three covered 10.6 of the 40.0 hours (27%). The median hold was 35 minutes. Three hot-file leases began within one minute of the previous one ending, which is what work waiting on a lease looks like. That last point is inferred, because refused claims are not logged anywhere. With one coordinator the cost was sequencing. With two coordinators that each touch docs at this rate, the same three files are leased for a larger share of the day. That share is a guess, not a measurement.

### 8. No combined view

Observed. `walk` printed one line per coordinator in store order, each with its own recorded mode. It shows no repository grouping, no queue state, no leases, and no blocked tickets. `close` reports one coordinator.

### 9. Work landed by a sibling

Observed in push mode. `engine/D1` submitted `E1` and `docs/D1` submitted `E2`. `docs` ran `land` and printed `landed E1 (engine/D1), E2 (docs/D1)`. `engine`'s next `land` printed `nothing to land`. `land.py status` without an id printed the mode, the trunk ref, and counts, with no holders. `dishes.tsv` has no column for the entry id, so `engine` learns its work landed only if its thread still remembers `E1` and asks `status E1`.

In merge mode the same run opens the PR. The landing skill tells "this thread" to call `watch_pull_request` on the PR that its `land` opened, so `docs` would watch `engine`'s PR, and `engine` would never learn the URL. This is inferred from the skill text, not observed.

### 10. Lease expiry

Observed. A lease claimed with a short TTL expired. A sibling's claim on the same path succeeded, and the original holder's `submit` failed with `L6 is not an active lease held by docs/D9`. `fire` always claims the 6-hour default, and neither brigade nor its skill renews a lease. In the real store the longest lease was held 2.2 hours, and no lease outlived its expiry, so this gap has not bitten yet. It would bite when a coordinator stalls for hours with work in review, such as across a T3 restart overnight.

### 11. Store collision

Observed. The store directory for a project is the slug of the project root's last path component. `open --project-root $T/other/app --name docs` printed `exists $T/brigade/app/docs`, and that `restaurant.json` names `$T/app`. The caller then runs a coordinator for the wrong repository.

### 12. Renew breaks the lease invariant

Observed. `docs/D9` claimed `README.md` as L6 with a short TTL. After it expired, `engine/D9` claimed `README.md` as L7. `lease renew L6` printed `L6 renewed`, and `lease list` then showed both L6 and L7 active on `README.md`. `renew` checks only that the lease state is `active`, not that it has expired or that its paths are still free. Once change 6 has `watch` renew leases, this bug would trigger every time a lease lapses, so change 2 fixes it first.

## Design rules

- **Shared repository facts live in the landing store.** The lease table already serializes every claim in one SQLite `BEGIN IMMEDIATE` transaction. A repository cap enforced inside that transaction cannot be raced by two coordinators starting work at once. A cap computed by reading sibling `dishes.tsv` files can be raced.
- **Remove a shared write before locking it.** Each intake source has one owning coordinator, so no two coordinators file tickets for one source. Where a shared step remains, it is one atomic operation. A store directory is claimed by `mkdir` without `exist_ok`, and a handoff is published by writing a temporary file and renaming it. Reading a sibling's tables is for display and recovery, never for exclusion.
- **Siblings are read from the existing layout.** A coordinator's siblings are the other `<store>/<project>/*/restaurant.json` files in its own project directory whose `projectRoot` equals its own. The only new shared files are the handoff and request files in each coordinator's `inbox/`.
- **Each coordinator stays the only writer of its tables.** A handoff writes a new file into the target's `inbox/`. It never appends to a sibling's `rail.tsv`.
- **`watch` reports and the coordinator decides.** Nothing starts automatically when a lease frees. Grouping tickets is the coordinator's judgment.
- **The liveness schedule follows `watch`.** A coordinator keeps its liveness schedule while `watch` prints anything other than `no work in progress`, and creates it the first time `watch` would print a line. `watch` prints a line for every item not `merged` or `dropped`, every blocked ticket, and every undelivered handoff.
- **Authority is checked at the write.** Every store write and every landing write carries its owner's token and checks it inside the same lock or transaction as the write (change 6). Stopping a run is a courtesy, because T3 does not promise that a run's commands end with it.
- **Delete duplicated state instead of syncing it.** The landing mode lives only in the landing contract.

## The executive admin

The user stays in charge of every coordinator, as brigade's skill already says. The executive admin works for the user on one repository, in two ways. As an assistant, it keeps the user up to date across every coordinator on that repository, forwards requests, files shared intake once, and writes one plain-language update. As a coordinator of coordinators, it settles conflicts between them on its own authority, by published rules, and logs every ruling so the user can review and overrule it. It escalates only what the rules cannot settle. Each coordinator keeps owning its own work, its reviews, its queue entries, and its `menu.md`.

### Who decides what

- **The scripts enforce.** The repository cap stays in `land.py` (change 2), path exclusion stays in leases, and duplicate intake is prevented by intake ownership (change 4). A thread cannot enforce a cap against two coordinators starting work at once, so every ruling is carried out through a script wherever one exists.
- **The admin rules on conflicts between coordinators.** It decides contested paths, ownership of a request that fits two purposes, each coordinator's share of the repository cap, and queue order between two coordinators' work, by the rules in [Rulings](#rulings). A coordinator must comply, and may appeal.
- **The user sets the rules' inputs and has the last word.** The user sets the repository cap, the landing mode, every purpose, and the priorities the rules read. The user answers every decision, and can overrule any ruling.
- **Each coordinator keeps its own work.** What it builds, how it reviews, and when it submits, absent a conflict, stay its own. A `from-user` request is a message from the user, and a coordinator can decline one with a reason, which the admin passes on. A ruling is not a request. When the admin's thread is gone, every coordinator keeps working and falls back to replying to the user itself. The admin is optional. Changes 1 to 7 work without it.

### What it does

| Duty | How |
| --- | --- |
| Routing requests | A request the user sends to the admin goes to the coordinator whose purpose fits, by `ticket move` and the `ticket` line. When two fit, an ownership ruling decides. When none fits, it asks the user. A coordinator that finds a routed ticket off its purpose moves it back and sends `misrouted`. |
| Shared intake | For a repository where several coordinators would read the same source, such as its GitHub issues, the admin is the intake owner from change 4. It files each issue once and routes it. It starts nothing. |
| Splitting the cap | It splits the repository cap the user set into shares by the share rules, and sets them with `land.py share`. When a repository sits at its cap while tickets wait for an hour, it tells the user and proposes a new cap with a default. It runs `land.py cap` only when the user asks. |
| Ruling on conflicts | It rules on contested paths, including hot shared files, and on queue order between coordinators, by [Rulings](#rulings). It finds conflicts in `blocked` rows older than an hour, in `contest` lines, and while routing. It never takes a lease away. |
| The landing mode | It runs `land.py mode` only when the user asks, and then tells every coordinator on that repository. |
| One update | It writes one plain-language update across all coordinators, at the user's reporting level. |
| Opening coordinators | When the user asks it to open a coordinator, it runs the opening steps, asks the user the opening questions, shows any overlap with the purposes of coordinators already on that repository, and launches the new thread once the user agrees. |

### Rulings

The admin rules on four kinds of conflict between coordinators, on its own authority. It decides by the rules below, applied in order, and the first rule that separates the parties decides. A ruling binds the coordinators involved until it is done, expires, is superseded, or the user overrules it.

The rules read three inputs.

- Each coordinator's `menu.md`, its purpose and its `## Off the menu` exclusions.
- The user's priorities, a ranked list of coordinator names under `## Priorities` in the admin's own `menu.md`, highest first. A coordinator the list does not name ranks below every named one, level with the other unnamed ones. Only the user changes the list.
- Age, meaning how long the waiting work has waited. For a blocked ticket it counts from its first `blocked` row. For a coordinator, it is the age of its oldest waiting ticket. For queue order it counts from the `contest` line.

| Kind | Question | Rules, in order |
| --- | --- | --- |
| Contested paths | Which coordinator claims a contested path next, including a hot shared file such as `README.md` | 1. A path that one coordinator's purpose names and the other's `## Off the menu` excludes goes to the first. 2. The user's priorities. 3. The older waiting work. |
| Ownership | Which coordinator owns a request that fits two purposes | 1. A coordinator whose `## Off the menu` excludes it loses. 2. The user's priorities. 3. The coordinator whose open work already touches the request's paths or ref. 4. Otherwise it is a real priority call, and the admin escalates. |
| Shares of the cap | How many of the repository's changes in flight each coordinator may hold, out of the cap the user set | 1. Each coordinator with waiting work gets one, in the order of the user's priorities, then age, until the cap runs out. 2. What is left goes by the user's priorities, highest first, up to each coordinator's waiting work. 3. A tie goes to the older waiting work. |
| Queue order | Which of two coordinators' passed items lands first when one would break or conflict with the other | 1. An item the other depends on lands first, as either coordinator or its verifier stated in a `contest` line. 2. The user's priorities. 3. The older `contest` side, meaning the item whose coordinator was waiting first. |

When the two ages differ, age decides. When they are equal, no rule separates the parties, and the admin escalates. So every ruling either has one outcome or escalates.

A live lease is never taken away. A contested-path ruling decides who claims next when the lease frees, and keeps the holder from starting new work on those paths while the winner waits. A share counts in the same unit as the cap, changes in flight, which are unreleased leases (change 2). Shrinking a share stops no running work. It only refuses that coordinator's next admission until it is back under its share.

Each ruling is carried out by a script wherever one exists (change 8).

- **Contested paths.** The admin runs `land.py lease reserve --for <winner>/ --paths <paths> --ruling R<n>`. Every admission, whether `lease claim` or the re-admission of an expired lease in `lease renew`, refuses another holder's overlap with a standing reservation. A reservation arms, which starts its 2-hour clock, only when no other holder's live lease overlaps it and the cap and the winner's share have room for one more change. Arming is itself an admission, done in the same transaction as claims, oldest reservation first. An armed reservation counts toward the cap and the share as one change in flight, so the winner always has room to claim. It stops counting once the winner holds a lease taken from it, so one piece of work never counts twice. A winner's claim releases only the reserved paths it covers. The rest stay reserved. A reservation that expires unused ends its ruling as `expired`, and the admin rules again on its next service if the conflict remains.
- **Ownership.** `ticket move` to the winner.
- **Shares of the cap.** The admin runs `land.py share --for <coordinator>/ <n>` for each coordinator, which `lease claim` and re-admission enforce in the same transaction as the cap. `land.py share` refuses shares that add up to more than the cap. A coordinator's `--workers` (change 5) stays its own limit on running agents, and is not a share.
- **Queue order.** The coordinator that finds the conflict runs `land.py contest --holders <its item's holder>,<the other item's holder>` before it sends the `contest` line. That prints `C<n>`. While the contest is open, `land` holds every entry of both holders, queued now or submitted later, out of every batch and, in `human` and `merge` mode, out of PR opening. So neither side can land before the ruling. When one holder's item is already landing, awaiting merge, or landed, `contest` refuses, because there is nothing left to order. An earlier bounced entry does not count. The admin carries out the ruling with `land.py contest --settle C<n> --first <holder>`. From then on `land` holds the second holder's entries until an entry of the first holder lands, so a bounce and a resubmit of the first item keep the order. Settling again with the other holder first replaces the order while neither has landed. `--settle` refuses an order that would close a cycle with another settled contest.

**The ruling log.** Before it carries a ruling out, the admin records it with `brigade.py rule add` in `rulings.tsv` in its own store. Each row holds an id `R<n>`, the time, the kind, the parties, the question, the rule that decided, the decision, the ruling it supersedes, and a state. The deciding rule is one of `purpose`, `priority`, `age`, `related-work`, `dependency`, `floor`, or `user`.

A ruling starts `in-force`. It becomes `done` when its condition ends. That means the reservation was claimed in full, the moved ticket appears in the winner's `rail.tsv`, the share is in place, or the first holder's entry landed after a settled contest. It becomes `expired` when its reservation runs out or its entry left the queue unordered. It becomes `superseded` or `overruled` when a later ruling replaces it.

Recording comes first, so a crash never leaves a ruling carried out but unlogged. Every service first reconciles each `in-force` ruling with what the scripts report, and marks it `done` or `expired` when its condition already ended. Then it carries out the ones still `in-force` again, which repeats nothing. `lease reserve` with the same ruling returns the same reservation. `ticket move`, `land.py share`, and `land.py contest --settle` give the same result when rerun.

**Replacing a ruling.** A new ruling that changes an earlier one, whether from an appeal or an overrule, names it in `supersedes`. The admin removes the old ruling's constraint before it carries out the new one. It runs `lease unreserve` on the old reservation, settles the contest again with the new first holder or cancels it with `land.py contest --cancel`, or sets the new shares. A coordinator checks the ruling's state in the admin's `rulings.tsv` before it acts on a `ruling` line, and drops a line whose ruling is no longer `in-force`. So a stale request file replayed after a replacement does nothing.

**Review and overrule.** Every update lists the rulings made since the last one, each with the rule that decided it, in plain words. The user can overrule any ruling by describing it. The admin runs `rule overrule R<n> --decision "<the user's words>"`, which marks it `overruled` and records a new ruling decided by `user` that supersedes it, then carries the new one out. A conflict the user settles before any ruling covers it, such as which of two items lands first, is recorded the same way, with `rule add --rule user`. An overrule changes what happens next. It cannot undo what the old ruling already caused, such as a lease already claimed or work already landed, and the admin says so. When the overrule states a general preference, the admin asks whether to add it to `## Priorities`, and adds it only when the user says yes.

**What it escalates.** The admin asks the user only what the rules cannot settle. It parks each as a decision with `86 add`, with options and a default, and acts on that conflict only after the answer.

- A real priority call. No rule separates the parties, as in an ownership case where no exclusion, priority, or related work decides, or an exact tie. Or the rules keep ruling against one coordinator, which lost three rulings in a row on the same paths, or whose work has waited on rulings for more than 24 hours. Or an ordered entry has waited more than 24 hours for an item that keeps bouncing. Those thresholds are starting guesses for the live run to tune.
- A change to a purpose. The same two purposes collided in more than three rulings in a week, or a request fits no purpose. The admin proposes new wording. It never edits a coordinator's `menu.md`.
- Anything irreversible. That covers dropping or closing another coordinator's work, deleting a branch, and changing the repository cap or the landing mode, which belong to the user.

**Coordinators comply, and can appeal.** A coordinator carries out a ruling for its own side. When it disagrees, it still complies and sends `appeal`. The admin rechecks the ruling with the appeal's facts, such as a dependency it did not know. When the rules now decide differently, it records a new ruling that supersedes the old one. Otherwise it keeps the ruling and lists the appeal in the next update for the user to review. When compliance would be irreversible, the coordinator holds instead of complying, and the admin escalates.

### One admin per repository

The first version serves one repository, the one in the user's request. Its store is `<store>/<project>/.admin/`, in the same project directory as the coordinators it serves, and its `restaurant.json` names their `projectRoot` and holds `role: "admin"`. `slug` never produces a leading dot, so `.admin` never collides with a coordinator's name. `walk`'s `*/*/restaurant.json` pattern does list it, because `pathlib`'s glob matches names that start with a dot, so `walk` prints it by its role.

The admin is a sibling of every coordinator on its repository, so the sibling rules carry it with no new mechanism. Intake ownership (change 4) counts its `intake` list, `ticket move` reaches it and leaves it, and handoff ids stay qualified by store path, as `app/docs/T6`. Its thread runs in the repository's T3 project, so every message stays inside one project. A coordinator with `reportsTo` keeps an hourly schedule that runs a service, even when it owns no intake, and every service begins with `inbox take`. The admin reads each coordinator's events from its `log.tsv` on every service, so it misses nothing when a coordinator's message fails.

An admin that spans several repositories or T3 projects is a later change. It needs repository-qualified intake, cross-project routing, and a test of whether `t3_thread_send` reaches a thread in another project. None of that is needed to coordinate, rule, route, and report for one repository.

### Messages

A thread launched with `t3_thread_launch` does not wake its launcher, so every exchange is an explicit `t3_thread_send`, following the convention Autopilot already uses. A coordinator sends with `mode: "queue"`, so it never interrupts a turn in progress. The admin sends with `mode: "auto"`, so the coordinator wakes. Each message is one line that starts with a fixed word and names the coordinator.

Messages are wakes, and the stores are the record. No message carries state that is not already durable in a store, so there is no separate record of sends. A send that fails is retried or left to the next scheduled wake. A wake that arrives twice is harmless, because each side consumes by a durable identity.

- **A coordinator event** is a row in that coordinator's `log.tsv`, identified by its store path and the byte offset where the row starts. The admin consumes events only through `sync`, which reads rows past a cursor and records each one once (change 9). A second `merged` line for one landing wakes the admin, and `sync` finds nothing new.
- **An admin request** is a file in the coordinator's `inbox/`, named by its request id `A<n>`. The admin passes that id as the `clientRequestId` of the `t3_thread_send` that wakes the coordinator, so a retried send delivers once. The coordinator acts on the file and runs `inbox done <id>`. A replayed file repeats nothing, because every action is keyed by its id. A routed ticket's wake uses its handoff id the same way.

The admin's service reads every coordinator's `log.tsv` from a cursor, the byte offset where its last service stopped reading that coordinator. It keeps one offset per coordinator in its own `restaurant.json`. A cursor always sits at a record boundary, just past a newline that ends a complete row. Every append discards an unfinished tail before it writes one complete row (change 4), so every complete row past the cursor is new, whatever its timestamp. `sync` copies the bytes past the cursor under a shared lock on the coordinator's `restaurant.lock`, so no append or tail repair runs during the copy (change 9). An unfinished last line is never read, and the writer's next append discards it. A lost message delays a reply and never drops an event.

Coordinator to admin:

| Line | Sent when |
| --- | --- |
| `merged <coordinator>: <title> [<pr url>]` | work lands. `push` and `local` modes have no PR URL |
| `sent-back <coordinator> D<n>: <one line>` | a review sends work back or blocks it |
| `decision <coordinator> Q<n>: <question> Options: <options>. Default: <default>.` | it parks a decision for the user |
| `failed <coordinator>: <one line>` | a failure or a paused queue it cannot fix itself |
| `drained <coordinator>: <closeout path>` | its batch drains |
| `report <coordinator>: <closeout path>` | its evening report is written |
| `blocked <coordinator> T<n>: waiting on L<n> held by <holder> since <time>` | a ticket has been blocked for more than an hour |
| `misrouted <coordinator> T<n>: <why>` | a routed ticket is off its purpose, after it moved the ticket back |
| `reply <coordinator>: <one line>` | its answer to a request from the user, including a decline and its reason |
| `contest <coordinator> C<n> D<n>: <one line>` | its item and another coordinator's would conflict in the queue, after it opened contest `C<n>`, naming which depends on which |
| `appeal <coordinator> R<n>: <why>` | it disagrees with a ruling, after it complied, or instead of complying when compliance would be irreversible |

Admin to coordinator:

| Line | The coordinator |
| --- | --- |
| `ticket <coordinator>: run ticket take` | takes the routed ticket |
| `from-user <coordinator>: <the user's words>` | treats it as a message from the user, and answers with `reply` |
| `answer <coordinator> Q<n>: <answer>` | records the user's answer with `86 answer`, then acts on it |
| `reports-to <coordinator> <thread>` | runs `set --reports-to <thread>` |
| `ruling <coordinator> R<n>: <decision>` | checks that the ruling is still `in-force` in the admin's `rulings.tsv`, then carries out its side, which for most rulings means waiting while a script enforces it |

Contested paths, ownership, shares, and queue order are recorded as rulings, and a `ruling` line tells each coordinator involved. A mode change and any other instruction from the user travel as `from-user`, with the user's words quoted.

Every admin line is durable. Before it sends, the admin runs `request --to <coordinator> "<line>"`, which writes the line as a request file in the coordinator's `inbox/` and prints its id (change 9). A routed ticket's line is the exception, because the handoff file is already its record.

A coordinator's `inbox take` files routed tickets, as `ticket take` does, and prints each request file's id and line. The coordinator acts on it as the table says, then runs `inbox done <id>`. A crash between acting and `inbox done` replays the request, so every action is keyed by the request id. A `from-user` request becomes work only through `ticket add --request <id>`, which refuses a second ticket for the same request id. Work starts only from tickets, which `fire` refuses once they are no longer waiting. Setting a value, recording an answer, and carrying out a ruling give the same result when repeated. So a replayed request repeats nothing.

Every coordinator event is durable too, because it is a row in the coordinator's own `log.tsv`. The admin's service reads those rows past its cursor and acts on them. A decision is an open row in `86.tsv`. A blocked ticket is a `blocked` row from change 5 with no later start. A merge and a send-back are state rows. A drain is a status with no work in progress. The message lines in the table above only wake the admin sooner. When a coordinator's send fails, it also falls back to replying to the user at its own reporting level, so the user still hears.

### What it never does

- Decide what belongs to the user. It sets no repository cap, landing mode, priority, or purpose, and never answers a coordinator's decision. It rules only on the four kinds of conflict, by the rules, and logs every ruling.
- Direct a coordinator's own work. Rulings settle conflicts between coordinators. What a coordinator builds, how it reviews, and when it submits, absent a conflict, stay its own.
- Write code, or edit any file in a repository.
- Land work. It never runs `land.py submit` or `land.py land`, and never merges or deletes a branch. Each coordinator owns its queue entries, PRs, and watches (change 6).
- Override a review. It never records or changes a verdict, never asks a coordinator to submit work that did not pass, and never messages a worker. When the user disagrees with a verdict, the user's words go to that coordinator as `from-user`.
- Write into a coordinator's store, except new files in its `inbox/`, which are routed tickets and request files. `Restaurant.log` in `brigade.py` rewrites `restaurant.json` on every event, so a second writer there would lose updates.
- Release, renew, or claim a lease, or start work. It only reserves contested paths for the winner of a ruling. The admin store refuses `fire`, `brief`, `dish`, `pass`, and `watch`.

### How the user opens it

The user asks any thread for an executive admin, through the brigade-admin skill.

1. Ask the user for the reporting level with the host's question tool, unless the user already said it. Recommend `digest`, because the admin exists so the user hears less.
2. `python3 <skills>/brigade/scripts/brigade.py open --admin --project-root <root> --reporting <level>`. It creates `<store>/<project>/.admin/` with `mkdir` and no `exist_ok`, so there is one per repository. A second open prints `exists`, and only the caller that got `opened` launches a thread. It prints every coordinator on the repository, with its purpose, as `open` prints siblings.
3. Write the user's priorities under `## Priorities` in its `menu.md`, with the user, highest first. Add which intake sources it should own. The rules read the priorities. Without them, the rules fall back to purposes and age.
4. Move shared intake. Each coordinator that lists the shared source runs `set --intake` without it. Change 4 refuses that while it still has waiting or assigned tickets from the source, so it finishes them first or moves them to the admin with `ticket move`. Then the admin store runs `set --intake <source>`.
5. Launch the thread with `t3_thread_launch` in the repository's T3 project, with `workspaceStrategy: {"type": "root"}`, title `Executive admin`, and the message "Use the brigade-admin skill. You are the executive admin for the store at `<store>/<project>/.admin`. Wait for the start message." Record it with `set --thread`. Then send it "Run your first service." with `t3_thread_send` and mode `"auto"`. Recording the thread before its first service lets that service pass the fence below.
6. The admin's first service sends each coordinator the `reports-to` line.

### Its services

First service pins the thread with `t3_thread_organize`, and creates three schedules bound to it, recorded with `set --schedule`. Intake runs every hour, `3600000`, because each service also runs the idle check, which must run well inside the 6-hour lease expiry. The 09:00 service runs routing and checks. The evening update runs at 18:30, after the coordinators' 18:00 reports. It creates no liveness or drain schedule, because it runs no workers and owns no queue entries.

Every wake, whether a schedule, a message, or a user message, runs one service.

1. Run `status`, which prints `owner <thread>@<generation>`. When it names another thread, end the turn with no action. Otherwise every command in this service runs as `$B --owner <thread>@<generation>`, and every `land.py` write passes `--owner .admin/@<generation>`. This step ends a stale wake early. The owner check inside each write is what stops a replaced or retired thread from writing (change 9).
2. Read its `menu.md`, `status`, `86 list`, and `walk --repo <root> --stale-hours 3`.
3. `inbox take`, for tickets moved back. Then intake from its owned sources with `ticket add --source <source>`. Then `request --republish`, which publishes again any request file a crash left unwritten.
4. Route each waiting ticket with `ticket move` and the `ticket` line. A ticket that fits two purposes gets an ownership ruling. A ticket no purpose fits becomes a question for the user with `86 add`.
5. Run `sync`, which reads each coordinator's `log.tsv` rows past its cursor, records them in the admin's own `log.tsv`, and advances the cursor. Rule on each conflict it finds, such as a block older than an hour, a `contest` or `appeal` line, or a changed share, per [Rulings](#rulings). Record each ruling with `rule add` before carrying it out. Then reconcile every `in-force` ruling with what the scripts report, mark the ones whose condition ended `done` or `expired`, and carry out the rest again, which repeats nothing. Pass coordinators' decisions, and whatever the rules cannot settle, to the user.
6. A coordinator that `walk` marks idle while it holds leases becomes a question for the user, before its 6-hour leases lapse.
7. Reply per the user's reporting level.

### Recovery and retirement

The store outlives its thread. Recovery is a user request, run from one thread, and it claims the store before it touches anything. It runs `set --thread recovering:<its own thread id> --replace --expect <old>`, a compare-and-swap. Of two recoveries racing, one wins and the other exits 1 before it changes anything. The claim records the old thread as `previousThread`.

**The owner token is the safety.** The admin's `restaurant.json` holds the recorded thread and a `generation`, and every replacement of the thread adds 1 to it. A service passes the token it read at its fence to every command. Each `brigade.py` write checks that token under the store lock, and holds the lock through the write. A token that no longer matches exits 1 with `brigade: owner <token> is stale; this store is owned by <thread>@<generation>`, and changes nothing. `set --thread` raises the landing store's floor for `.admin/` to the new generation before it rewrites `restaurant.json`. Each `land.py` write the admin makes checks its `--owner` against that floor in the same transaction as the write (change 8). So a command the old run started, whenever it finishes, either completed before the claim or is refused after it. That holds for a command T3 did not kill when the run ended, and for a run that never ends.

The steps below stop the old run before a new thread starts, so its commands end instead of failing one by one. They are a courtesy. The fence does not depend on them.

1. Delete the schedule ids the claim printed with `delete_scheduled_task`, and clear their names, so no new wake starts.
2. When the old thread still exists, call `t3_thread_interrupt` on it. A result of `status: "interrupt_requested"` means the run has not stopped yet.
3. Call `t3_thread_wait` on the run id that `t3_thread_interrupt` returned, or on the thread with no run id when it returned none. An idle thread returns at once with `status: "idle"` and no run id.
4. When the wait returns `timedOut: true`, recovery stays pending. The store keeps `recovering:<its own thread id>`. The recovering thread tells the user, launches nothing, and waits again on its next turn, on the thread in `previousThread`.
5. When the wait reports a terminal state, archive the old thread. Launch the new thread with the waiting message from opening step 5. Run `set --thread <new> --replace --expect recovering:<its own thread id> --stopped <run id>` with the run id the wait reported, `--stopped idle` when the wait reported an idle thread, or `--stopped gone` when the old thread no longer exists. Then send the start message.

`set --thread` refuses to replace a `recovering:` value without `--stopped`. `--stopped` is evidence the recovering thread asserts, recorded in `log.tsv` for audit. The script cannot check it, and the fence does not rely on it. The new thread's first service sends every coordinator the `reports-to` line. Pending tickets, owned intake, and every ruling the old thread recorded before the claim survive in the stores, and that service reconciles them as any service does. When the recovering thread is itself gone, a later recovery claims with `--expect recovering:<that thread id>`, keeps `previousThread`, and runs the same steps.

Retiring the admin routes or drops its waiting tickets, then clears its intake with `set --intake ""`. It deletes its schedules with `delete_scheduled_task`, clears each name with `set --schedule <name>=`, sends a last update, and unpins its thread. Last, `set --thread "" --replace --expect <its own id>` clears the recorded thread and raises the generation, so any later wake stops at the fence and any command still running exits as a stale owner. Each coordinator then runs `set --reports-to ""`, and takes a shared source back with `set --intake <source>` where the user wants it. Restarting a retired admin is recovery with `--expect ""` in place of the old thread and `--stopped gone`.

### What the user hears

The user hears from one thread. A coordinator whose `restaurant.json` has `reportsTo` replies to the user only when the user writes to it directly. Its own reporting level stops mattering. It sends every event in the table above, whatever its level, because the admin's level filters replies, and it cannot filter events it never received. Its `close --to-file` still writes its full report into its own store.

The admin's level uses the same three values as a coordinator's. At `every-turn` it replies after each of its own wakes, and each message is a wake. A coordinator's routine wake sends no line, so the user stops hearing about routine wakes. At `milestones` it replies when any coordinator's work merges, when a review sends work back or blocks it, when the user has a decision to make, or when a failure arrives. At `digest` it replies for a decision, a failure that no coordinator can fix itself, one summary when every coordinator has drained, and the evening update. A ruling is never a reply occasion on its own at `milestones` or `digest`. Each update lists the rulings made since the last one in plain words, with the rule that decided each, and says that the user can overrule any of them by describing it. The full update file holds each ruling's id.

Every admin reply is plain language at every level, written as brigade's Digest messages rules say. A few sentences say what changed for each purpose, what is next, and what the user must decide, each decision with its default. It leaves out work ids, SHAs, paths, branch names, and tool names. It names a coordinator by its purpose, not its store name. Merged PRs may follow as plain titles linked to their URLs.

The reply ends with one line naming the full update, which `close --to-file` writes in its store. The service copies each coordinator's events into the admin's own `log.tsv`. So that update is the admin's ordinary report of its own log, plus the newest report path of each coordinator.

A message from the user gets at least a one-line acknowledgment at every level, and a direct question gets an answer, as for any coordinator. A coordinator's decision keeps its home in that coordinator's `86.tsv`, and the user's answer goes back as an `answer` line. The admin's own questions, such as a ticket no purpose fits, live in its own `86.tsv`.

### Replaces or adds, gap by gap

| # | Gap | With an executive admin |
| --- | --- | --- |
| 1 | Duplicate intake | Replaces the owner. For a repository the user names, the admin owns the shared source, so no coordinator does. Change 4's mechanism is unchanged. |
| 2 | No cap across coordinators | Replaces each coordinator choosing its own share. `land.py cap` still enforces the total the user sets, and the admin rules each coordinator's share. |
| 3 | No handoff | Adds. `ticket move` stays the mechanism, and coordinators keep moving tickets to siblings themselves (change 4). The admin also routes the user's requests and shared intake, and rules ownership when a request fits two purposes. |
| 4 | Overlapping purposes | Adds. `open` still prints siblings. The admin shows the user any overlap before a new coordinator launches. |
| 5 | Blocked tickets | Replaces the race. `watch` still reports. When a block lasts an hour, the admin rules who claims next and reserves the paths for the winner, so when the lease frees only the winner's `fire` succeeds. |
| 6 | Mode drift | Replaces one step. Change 7's coordinator running `land.py mode` and telling each sibling becomes the admin, acting when the user asks. |
| 7 | Hot shared files | Replaces "each coordinator batches its own". Hot shared files get the contested-path rules. Doc follow-ups go to the admin, which routes them by the ownership rules. |
| 8 | No combined view | Replaces the user-facing part. The admin's update is the combined view of its repository. Grouped `walk` (change 7) stays as its data source, and the view across repositories. |
| 9 | Work landed by a sibling | Neither. Each coordinator settles its own entries (change 6). |
| 10 | Lease expiry | Adds a little. `walk --stale-hours 3` shows a coordinator idle for 3 hours, and the admin asks the user before that coordinator's 6-hour leases lapse. |
| 11 | Store collision | Neither. |
| 12 | Renew breaks the lease invariant | Neither. |

Queue order between two coordinators' work is a conflict the gap list did not name. The admin rules it, and `land.py contest` (change 8) enforces it.

## Changes

Each change is one PR through the landing queue, with its own tests and its own changelog fragment (change 1). Every change that edits a skill's behavior needs a fresh-child test per the `pstack-author-skill` skill. Every exclusion the design promises across two coordinators gets a test that runs two processes at once, because the experiment ran commands one after another.

### Change 1. Changelog fragments and a docs batch rule

Closes gap 7 for `CHANGELOG.md`, and sets the rule for `README.md` and `docs/guide.md`.

- **Repository practice.** Each user-facing change adds one file directly under `changes/` holding its one Unreleased bullet. The file name is the branch name with `%` written as `%25` and `/` written as `%2F`, plus `.md`, so `docs/a` writes `changes/docs%2Fa.md` and `docs-a` writes `changes/docs-a.md`. The encoding is reversible and the directory is flat, so two branch names never share a path. A coordinator's branches are `<slug>/<item id>`, and item ids never repeat, so its names are never reused. Any other branch name reused before a release adds its bullet to the same file. `CHANGELOG.md` loses its `## Unreleased` section, and its current bullet moves into a fragment. At release, `CONTRIBUTING.md` lists the fragments in the order they were added (`git log --reverse --diff-filter=A --format= --name-only -- changes/`), writes their bullets under the new version heading in `CHANGELOG.md`, and deletes them in the same commit.
- **Why fragments and not PR bodies.** The other candidate keeps changelog lines in PR bodies and collects them at release. Fragments work in every landing mode, and `push` and `local` open no PR. They need no `gh` call at release time, and the reviewer reads the line in the same diff as the change.
- **README.md and docs/guide.md.** These are prose, so fragments do not fit. A house rule says that a change edits `README.md` or `docs/guide.md` only when its ticket is about them, or when it removes or renames something they name. Otherwise the worker lists the needed doc edit under follow-ups in its report, and the coordinator files it as a ticket. When a sibling's `menu.md` claims the docs, the coordinator moves that ticket to it with `ticket move` (change 4). When no coordinator owns them, each coordinator batches its own doc tickets into one docs item, and the lease orders the batches. The pstack-t3 coordinator already batched doc follow-ups this way twice, by hand. Change 3 adds the generic sentence to the brigade skill.
- **Files.** `CHANGELOG.md`, `CONTRIBUTING.md`, `tests/test_pstack_t3.py`, and this change's own fragment.
- **Test.** `tests/test_pstack_t3.py` fails when `CHANGELOG.md` has a `## Unreleased` heading, with a message that names `changes/`, and when a file under `changes/` holds anything but bullets or sits in a subdirectory. A worker that adds a changelog line the old way fails the suite. The release cut is the end-to-end check. It must produce the same `CHANGELOG.md` section that the fragments hold.
- **Coordinator use.** pstack-t3's standing orders gain the docs batch rule, and `CONTRIBUTING.md` drops "Add a line under Unreleased".

### Change 2. Repository change cap, a safe renew, and per-holder status in `land.py`

Closes gap 2 for the repository, gap 12, and the landing half of gap 9.

- **What the cap counts.** The repository cap bounds changes in flight, which are leases not yet released. That is every `submitted` lease and every `active` lease that has not expired. A worker that is running, a review in progress, and an entry waiting to land all hold such a lease. The count rises only on admission, and falls on release or when an active lease expires. A bounce moves a lease from `submitted` back to `active` and leaves the count alone, so no path exceeds the cap. An item started without `--paths` writes nothing and holds no lease, so it counts only toward its coordinator's cap (change 5).
- **`land.py init ... --cap N` and `land.py cap N`.** These store a `cap` key in the contract. `0` clears it. Absent means no cap.
- **Admission.** `lease claim` admits a lease inside its existing transaction. After the overlap check, it counts unreleased leases. When the count is at the cap it refuses with `repository at its cap: 3 of 3 changes in flight (docs/D1, engine/D1, engine/D2)`. The holders in the message are the facts a coordinator needs to say who it waits on.
- **`lease renew`.** Renewing a lease that has not expired works as today. Renewing an expired lease is a new admission in the same `BEGIN IMMEDIATE` transaction. It refuses when any other holder's unreleased lease overlaps, with `L1 expired and L2 held by engine/D1 now covers README.md; claim again after it is released`. It also refuses when the cap is full, with the admission message. An expired lease with no overlap and room under the cap renews.
- **`land.py status --holder <holder>`.** It prints the entries of exactly that holder in id order, one per line, with the SHA: `E1 landed (engine/D1, 1ebeef80f473) as 0f3a9c1d2e4b`, `E3 awaiting-merge (engine/D2, 34a807b9493f) <pr url>`, `E4 bounced (engine/D3, a1f7ed73e60c): conflict with trunk`. With `--holder` ending in `/`, it matches that prefix.
- **`lease check --holder <holder> --paths <paths>`.** It runs the admission test of `lease claim` without claiming. It prints `free`, or each overlapping lease with its holder, or the cap message. `watch` uses it to recheck a blocked ticket's requested paths (change 5).
- **`lease renew --if-live`** renews only a lease that has not expired, and otherwise refuses with `L4 expired at <time>`. `watch` uses it, so re-admitting an expired lease is always an explicit step a coordinator takes after it stops the old worker (change 6).
- **`lease renew` names why it refused.** The refusal names the lease's state, as in `L4 is submitted; the queue holds it`, `L4 is released`, the overlap message, or the cap message. `watch` maps each to its own line (change 6).
- **`land.py status`.** It adds `changes in flight: 3 of 4` to its line when a cap is set.
- **`land.py mode`.** Its success line ends with `; leases held by docs/D1, engine/D3` when any lease is unreleased, so the person changing the mode sees whom it affects.
- **Files.** `t3/added/landing/scripts/land.py`, `t3/added/landing/SKILL.md`, `tests/test_landing.py`, generated `skills/landing/`, its fragment.
- **Tests.** With a cap of 2, claims by `a/D1` and `b/D1` succeed, `c/D1` is refused with the literal message, and after `lease release L1` the same claim returns `L3`. Ten processes claiming disjoint paths at once under a cap of 3 produce exactly 3 leases. A submitted lease counts toward the cap, and a bounce leaves the count unchanged. An expired lease does not count. Renew of an expired lease after another holder's overlapping claim exits 1 with the literal message, and `lease list` shows one lease on the path. Renew of an expired lease after the cap filled exits 1. Renew of a submitted lease and of a released lease each print their own message. `lease check` on paths a released lease held prints `free`, and on paths a new lease holds names that lease. `status --holder engine/D2` lists only that holder.
- **Coordinator use.** The coordinator that opens first on a repository sets the cap with the mode, as `land.py init --trunk main --mode merge --cap 4`. The landing skill's setup section says the cap belongs to the repository like the mode does.

### Change 3. Sibling awareness in `open`

Closes gaps 4 and 11, and adds the hot-files sentence for gap 7.

- **`open` claims its directory atomically.** It creates the coordinator directory with `mkdir` and no `exist_ok`, then writes `restaurant.json`. The process that created the directory owns it. Any other process, whether it lost a race or found an existing coordinator, reads `restaurant.json`, waiting up to one second for it to appear. When that file names another `projectRoot`, `open` exits 1 with `brigade: <dir> already holds a coordinator for <other root>; pick another --name`. Making the project directory unique per repository would change the store layout for every existing coordinator. Refusing is enough, because siblings are matched by `projectRoot` and not by directory.
- **One thread per coordinator.** `open` on an existing coordinator prints `thread <id> already recorded` when one is. `set --thread` refuses to replace a recorded thread unless `--replace` is passed. The skill's opening step 6 launches a coordinator thread only when `open` printed `opened`. That word goes to exactly one caller, the one whose `mkdir` created the directory. An `exists` coordinator with no recorded thread is the user's call, so two threads never write one store.
- **`open` prints siblings.** After `opened <dir>` or `exists <dir>`, it prints one block per sibling:

  ```
  sibling engine (<store>/app/engine), thread <id or not recorded>
    purpose: Keep the engine fast and correct.
    off the menu: Docs and release notes; Vendor upgrades
  ```

  A sibling whose `menu.md` still has the template purpose prints `purpose: not written yet`.
- **Skill.** The skill's opening step 4 says to fill `menu.md`, keep its purpose clear of every sibling `open` printed, and list each sibling's purpose under its `## Off the menu` heading as that sibling's work. Two coordinators opened at the same moment both see template purposes, so the first service gains a step that reruns `open` and compares the purposes it prints with its own `menu.md`. Step 4's standing-orders list gains "the repository's hot shared files, and where their changes go instead", pointing at the fragment and docs batch rules.
- **Files.** `t3/added/brigade/scripts/brigade.py`, `t3/added/brigade/SKILL.md`, `tests/test_brigade.py`, generated `skills/brigade/`, its fragment.
- **Tests.** Open `Perf` with a written purpose and exclusions, then open `Docs` on the same root, and assert the exact sibling block. Open `Docs` on another root whose directory has the same name, and assert exit 1, the literal message, and an unchanged `restaurant.json`. Two processes opening the same name on different roots at once produce one `restaurant.json` and one refusal. `set --thread` on a coordinator with a recorded thread exits 1 without `--replace`.
- **Coordinator use.** Rerunning `open` on an existing coordinator reprints its siblings, so a coordinator can check for new siblings at any time.

### Change 4. One intake owner per source, and ticket handoff

Closes gaps 1 and 3.

- **Why ownership and not a shared claim.** Two coordinators that both read GitHub share one write, the ticket for each issue. Locking that write across two stores leaves windows, because `rail.tsv` and any shared claim cannot commit together. Giving each source one owner removes the shared write. The owner's own `rail.tsv` is then the only record of refs from that source, and its single writer makes the duplicate check race-free.
- **`restaurant.json` gains `intake`,** a list of source names set by `open --intake github` and `set --intake github`. Setting a source that a sibling already lists exits 1 with `brigade: docs already owns intake from github; move tickets to it instead`. Dropping a source exits 1 while this coordinator holds a `waiting` or `assigned` ticket from it. Two coordinators setting the same source at the same moment is the one window left. It is a one-time setup step, and the next check fails safe.
- **`ticket add --source <s>`** for any source other than `user` exits 1 unless this coordinator lists `<s>` in `intake` and no sibling also lists it. The refusal names the owner, as `brigade: core owns intake from github; ask it to file this and move it here`. When two siblings list one source, both refuse, so a setup race files nothing twice. `ticket add --from-report`, added later, runs none of this. Tickets it files get source `report`.
- **The same ref is filed once.** When `--ref` is not empty, `ticket add` also exits 1 when this coordinator holds a live ticket with the same ref, with `brigade: <ref> is already T1 (waiting); nothing added`. A `waiting` or `assigned` ticket is live. A `moved` ticket is as live as the ticket it was handed to, found by its handoff id in the target's `rail.tsv` and followed through each further move. A handoff not yet taken is live. So a ref moved twice and finished at the end of the chain frees itself, with no write to any other store. A `done` or `dropped` ticket does not block, so a reopened issue gets a new ticket.
- **A sibling's live ref also refuses,** by the same rule. That read of other coordinators' files is not exclusion. It covers an owner that took a source over from a sibling, whose old tickets stay live in the sibling's `rail.tsv`. Ownership is what excludes, so two limits remain and are accepted. Two coordinators can file the same ref as `user` tickets at the same moment, and one issue can arrive through two different sources that two coordinators own. Refs compare as exact strings after trimming whitespace. The intake step records the URL `gh` prints, so one issue has one ref.
- **`ticket move T6 --to <sibling>`.** The target must be a sibling. T6 must be `waiting`, or already moved to the same target.
  1. One atomic rewrite of `rail.tsv` sets T6 to the new state `moved` and its `dish` field to `to:<sibling>`. State and destination commit together. From here this coordinator cannot start work on T6, and its ref stays live here, so the owner's intake never refiles the issue.
  2. Publish `<sibling dir>/inbox/<handoff id with / written as ~>.json`, holding `summary`, `source`, `ref`, and the handoff id. The handoff id is the source store's path under the store root plus the ticket, such as `app/docs/T6`, so two projects that both have a `docs` coordinator with a T6 never collide. Slugs never contain `~`, so the file name maps back to one id. The file is written under a temporary name in `inbox/` and renamed into place.
  It prints `T6 moved to engine; tell thread <id>`. A rerun after a crash repeats step 2 unless the target's `rail.tsv` already holds the handoff id.
- **`ticket take`.** For each `*.json` file in this coordinator's inbox, in name order, it looks for a `rail.tsv` row whose `source` ends with `(from <handoff id>)`. When none exists, it rewrites the whole `rail.tsv` through the existing atomic temp-and-rename helper, with one new row whose `source` is `<source> (from <handoff id>)`. When the row exists and `log.tsv` lacks `from <handoff id>`, it writes that log row. Then it deletes the file. A crash at any point leaves either no ticket, or a complete ticket that the next take recognizes and finishes logging. Dedupe uses the handoff id, not the ref.
- **An append can never join two rows.** Today `Restaurant.append` opens `log.tsv` in append mode and writes. A killed append can leave an unfinished tail such as `2026-10-06T00:00:00Z<TAB>ticket<TAB>T6<TAB>waiting<TAB>fro`. The next append would write its row onto that tail, and the joined line would parse as one row whose note is `fro2026-10-06T00:00:01Z`. Ignoring a last line with no newline does not prevent that, because the join ends in a newline. So `append` changes in three ways.
  1. It takes an exclusive `fcntl` lock on `restaurant.lock`, a sidecar file in the store that is never replaced. A lock on the table itself would not hold for `rail.tsv`, whose rewrites replace its inode. Every write in `brigade.py` takes the same lock, so two writers in one store never interleave.
  2. Under the lock, it reads the file's last byte. When the file does not end in a newline, it truncates the file to the byte after its last newline, which discards only the unfinished tail.
  3. It writes the whole row, newline included, with one `os.write` on a descriptor opened with `O_APPEND`, then releases the lock.

  The truncation never removes a byte before the last newline, so a sync cursor that sits at a record boundary stays valid. Readers validate every row. `rows` skips an unfinished last line, and refuses a complete line whose field count differs from the table's header, or whose `at` field is not a timestamp, with `brigade: <table> line <n> is malformed; fix or remove it`. A malformed row stops the read instead of being consumed as a different event.
- **Handoffs stay visible until taken.** Until the target's `rail.tsv` holds the handoff id, the source's `watch` prints `T6: moved to engine, waiting for ticket take` while the inbox file exists, and `T6: moved to engine, not delivered; run ticket move T6 --to engine again` when it does not. The target's `watch` prints `handed to you: 1; run ticket take`. `status` adds `handed to you: N` while the inbox holds files. `close` gains a section for `moved` tickets, `Handed to another coordinator`.
- **Skill.** Open step 4 sets `--intake` for each source in the standing orders, and leaves a source to the sibling that already owns it. Run a service step 2 starts with `$B ticket take`. A ticket that is a sibling's work is moved with `ticket move`, followed by `t3_thread_send` to the printed thread with mode `"auto"` and the line `ticket <coordinator>: run ticket take`. Siblings share a project root, so they share a T3 project and can message each other.
- **Files.** Same as change 3.
- **Tests.** `set --intake github` in a second sibling is refused with the literal message. With `intake` written into both siblings' `restaurant.json` by hand, `ticket add --source github` exits 1 in both. The same ref is refused within the owner while live, and accepted after `done`. `ticket move` interrupted after step 1, then rerun, publishes one inbox file. `ticket take` run twice with the file copied back between runs files one ticket. A take killed after the `rail.tsv` rewrite and before the log row files one ticket and one log row on the next take. A failure injected inside the temp-file write leaves the same end state after the next take. A take killed inside the log append, which leaves the tail `<at><TAB>ticket<TAB>T6<TAB>waiting<TAB>fro`, is followed by a take that recovers it. Then `log.tsv` ends in a newline and holds exactly one row for the handoff, with kind `ticket`, id `T6`, state `waiting`, and note `from app/engine/T6`, and no line holds more than five fields. A hand-written joined line in `log.tsv` makes `ticket list` exit 1 with the literal malformed message. Two processes appending 200 rows each at once leave 400 rows that all parse. Dropping `github` from `intake` with a waiting github ticket exits 1. After a source moves to a new owner, that owner refuses a ref the old owner still holds live. `watch` prints the undelivered line when the inbox file is deleted before take.

### Change 5. Blocked tickets and the per-coordinator cap

Closes gap 5, and gap 2 for one coordinator.

- **`restaurant.json` gains `workers`,** set by `open --workers N` and `set --workers N`. A missing field reads as 2. The cap counts items with an agent running, which are `in-progress` and `in-review` items. `fire` refuses before it claims a lease when the count is at the cap, with `nothing fired: 2 of 2 workers running`. `dish --state in-progress` and `dish --state in-review` enforce the same cap whenever the item is not already counted, because a send-back, a bounce, and a retried review enter those states without `fire`. Moving from `in-progress` to `in-review`, and replacing the worker of an item, leave the count alone.
- **What this cap does not bound.** It bounds running agents. It does not bound one coordinator's share of the repository cap, because its submitted entries hold leases with no agent running. Without the executive admin, fairness between coordinators is out of scope for changes 1 to 7. With it, the admin's shares (change 8) bound each coordinator's part of the repository cap. `open` warns when `workers` is at or above the repository cap and a sibling exists.
- **A refused `fire` is recorded with what it needs.** On any refusal, `fire` logs a `blocked` row for each ticket in `log.tsv`. The note holds everything a later `fire` needs, as JSON with `kind` (`lease`, `repository`, or `workers`), `tickets`, `station`, `summary`, `paths`, and `timebox`. The ticket stays `waiting`, and `rail.tsv` keeps its columns. A later `fire` of that ticket clears the block.
- **`ticket list`** appends `blocked: <reason>` to a waiting ticket whose latest log row is `blocked`.
- **`watch` rechecks the real condition.** It runs `land.py lease check` on the recorded paths, and counts this coordinator's running workers. It prints `T2: waiting on L7 (docs/D3)`, `T5: waiting for room in the repository (4 of 4 changes in flight)`, or `T7: waiting for a worker (2 of 2 running)`, whichever holds now. A different lease that took the same paths after the first was released still blocks. When nothing blocks, it prints a runnable command built from the note, `T2: unblocked; run fire --tickets T2 --station bug-fix --summary '<summary>' --paths src/a.py,CHANGELOG.md --timebox 60`.
- **Skill.** Run a service step 4 drops its sentence about the cap in the standing orders, because `fire` enforces it. A refused `fire` leaves the tickets waiting. The liveness schedule follows `watch` per the design rule, so First service step 3 creates it on the first refused `fire`, and the Liveness check deletes it only on `no work in progress`. The Liveness check gains the `unblocked` line, which reruns Run a service steps 3 and 4 for those tickets. Open step 4 replaces "worker cap" in the standing-orders list with `--workers`.
- **Files.** Same as change 3.
- **Tests.** A sibling's lease refuses `fire`. Then `ticket list` shows the reason, and `watch` prints `waiting on L1`. After `lease release L1` and a new claim on the same paths, `watch` prints `waiting on L2`. After that release, it prints the literal `unblocked` line, and running that line starts the item. With `--workers 1`, a second `fire` is refused, and so are `dish --state in-progress` on a sent-back item and `dish --state in-review` on a blocked one. A repository-cap refusal prints the repository line.

### Change 6. `watch` keeps leases alive and settles work from the queue

Closes gap 10, and the brigade half of gap 9.

- **Lease renewal.** For each item in `in-progress`, `in-review`, `passed`, `sent-back`, or `blocked` that has a lease, `watch` runs `land.py lease renew --if-live` and reads its answer. A live lease gets a fresh 6-hour expiry, and `watch` prints nothing for it. `watch` never needs `lease list`, which hides expired leases. A submitted lease is left to the queue. A released lease prints `D3: lease L4 was released; claim again before submitting`. A landing store that cannot be read prints `D3: could not renew L4: <error>`. After a pass that renewed every live lease, `watch` updates `lastActivityAt` in `restaurant.json`, so `walk --stale-hours` measures whether a coordinator still keeps its leases alive.
- **An expired lease is re-admitted only after its worker stops.** `watch` prints `D3: lease L4 expired; stop its worker, then run lease renew L4`. The coordinator calls `t3_thread_interrupt` on the worker thread, then `t3_thread_wait` on the run id it returned. When the wait returns `timedOut: true`, the coordinator leaves the lease expired and the item as it is, and waits again on its next service. Only after the wait reports a terminal state does it run `lease renew L4` itself. That re-admits the lease, or refuses with the overlap message or the cap message from change 2. On a refusal the coordinator parks the item and runs the renew again on a later service.
- **A line for every open item.** Besides those, `watch` prints one line for each item not `merged` or `dropped` that has none yet, such as `D2: in review`, `D3: passed, not submitted`, or `D4: parked`. So a coordinator with only reviews, parked work, or passed work keeps its liveness schedule, and its leases keep renewing.
- **Leases end with the work, after the worker stops.** A requested interrupt is not a stop. `t3_thread_interrupt` can return `status: "interrupt_requested"` while the worker's run goes on. So dropping an item takes three steps.
  1. Call `t3_thread_interrupt` on its worker thread.
  2. Call `t3_thread_wait` on the run id it returned, or on the thread when it returned none. When the wait returns `timedOut: true`, the item keeps its state and its lease keeps renewing, and the next service waits again.
  3. When the wait reports a terminal state, run `dish D3 --state dropped --stopped <run id>`, or `--stopped idle` when the wait reported an idle thread, which releases the item's active lease.

  `dish --state dropped` on an item that holds an active lease and records a worker thread refuses without `--stopped`, with `brigade: D3 holds L4 and its worker may still be running; wait for its run with t3_thread_wait, then pass --stopped <run id>`. The lease stays active, so no sibling can claim its paths early. `--stopped` is an evidence assertion recorded in `log.tsv` for audit, which the script cannot check. The skill's closing section follows the same steps for every active lease. `brigade.py close` writes reports and releases nothing. A parked item keeps renewing, because its paths are still reserved for it.
- **A late worker command authorizes nothing.** The interrupt and wait are a courtesy that ends the old worker's commands early. The safety is that a worker holds no authority to outlive. It writes only its own worktree and branch, and runs no lease, queue, or store command. Only the coordinator submits, and `submit` refuses a lease that is not active and held by the item, with `L4 is not an active lease held by docs/D3; claim one before submitting`. So a command that outlives the worker's terminal run can add a commit to a dropped item's branch, and that commit can never be submitted. After a re-admission, a late commit stays on the item's own branch. It reaches the queue only inside an exact SHA a reviewer passed, and `submit` refuses it when it touches a path outside the lease.
- **Every store write checks its owner.** `restaurant.json` gains `generation`. `set --thread` sets it to 1 when it records a first thread, and `--replace` adds 1. `status` prints `owner <thread>@<generation>`. The skill's Run a service step 1 reads it and sets `$B` to `brigade.py --at <restaurant dir> --owner <thread>@<generation>`. Every `brigade.py` write in a store with a recorded thread requires `--owner`, except `set --thread`, which changes the owner and is fenced by `--replace`. The admin's store adds `--expect` in change 9. It compares the token with the recorded thread and generation under the store lock from change 4, and holds that lock through the write. A mismatch exits 1 with `brigade: owner <token> is stale; this store is owned by <thread>@<generation>`, and changes nothing. A coordinator thread replaced with `set --thread --replace` therefore cannot write again, even from a command it started before the replacement.
- **The landing store enforces the same generation.** `land.py` gains an `owner` table of holder prefixes and generation floors. `land.py owner --prefix docs/ --generation 2` raises a floor and never lowers it, so a rerun is a no-op. `set --thread --replace` runs it before it takes the store lock, because change 4 forbids a `land.py` call under that lock. Under the lock it reads `restaurant.json` again, and when the thread or generation changed since it raised the floor, it starts over. Then it rewrites `restaurant.json`. A crash between the two leaves a floor that the next replace reaches again. `lease claim`, `lease renew`, `lease release`, and `submit` take `--owner <prefix>@<generation>`, whose prefix the holder must start with. Inside the write's `BEGIN IMMEDIATE` transaction, each refuses a generation below the prefix's floor with `land: owner docs/@1 is stale; docs/ is at generation 2`, and refuses a holder under a floored prefix that passes no `--owner`. A prefix with no floor works as today. `brigade.py` passes its store's token on every `land.py` call it makes, and the skill's `$L` writes pass `--owner <slug>/@<generation>`. Lease release and re-admission therefore refuse a replaced coordinator's stale command and change nothing.
- **The limit of the guarantee.** A lease expires only when its coordinator has not run `watch` for 6 hours. From expiry until the old worker stops, another coordinator may claim and edit the same paths. The interrupt, wait, then renew order keeps that gap from growing after the coordinator returns.
- **Entries are matched exactly.** For each item in `passed` or `queued`, `watch` runs `land.py status --holder <slug>/<item> --sha <sha>` and takes the entry with the highest id it prints. `status --holder` prints a 12-character SHA, so `--sha` filters on the full SHA inside `land.py`, and two commits that share a prefix never match each other. It prints `D1: landed as E1 (0f3a9c1d2e4b); mark it merged`, `D2: E3 awaiting merge <pr url>; watch that PR`, `D4: E4 bounced: conflict with trunk`, or, for a `passed` item, `D5: E6 already submitted; mark it queued`. That last line recovers a crash between `submit` and `dish --state queued`. An older bounced entry at another SHA is ignored.
- **Bounce fix.** The skill's bounce step runs `dish --state in-progress` before it reruns `brief`. Today it reruns `brief` on a `queued` item, which `brief` refuses.
- **Skill.** The Liveness check acts on these lines with the steps the skill already has for a landing, an open PR, and a bounce. The landing skill's Keep the queue moving section says to act only on lines whose holder is this coordinator's own, and to call `watch_pull_request` only on those PRs. A sibling's PR is the sibling's to watch, and the owner learns its URL from the `awaiting merge` line. The drop step, the closing section, and the expired-lease step each say to wait with `t3_thread_wait` after `t3_thread_interrupt`, and to stop on a timeout. Run a service step 1 sets `$B` and `$L` with the owner token from `status`. A write refused as a stale owner ends the service with no further command.
- **Files.** Same as change 3, plus `t3/added/landing/`, `tests/test_landing.py`, and generated `skills/landing/` for the owner floor and the sentence on holders.
- **Tests.** A short-TTL lease on an in-progress item is renewed by `watch` before it expires, and its expiry moves forward. An expired lease makes `watch` print the expired line and stay expired, and the explicit `lease renew` then re-admits it, or prints the overlap message when another holder claimed the paths. A coordinator whose only item is `in-review`, `passed`, or `blocked` gets a `watch` line, not `no work in progress`. An item whose entry another holder's `land` landed makes `watch` print `landed as E1`. A passed item with a submitted entry prints `already submitted`. An item with a bounced entry at an old SHA and a queued entry at its current SHA prints only the queued state. These run against a scratch repository with a `local` contract, as the existing `fire` test does.
- **Drop test.** It models a worker whose interrupt returned `interrupt_requested` and whose write finishes later. D3 holds L4 on `README.md` and records a worker thread. `dish D3 --state dropped` without `--stopped` exits 1 with the literal message. `lease list` still shows L4 active, and a sibling's `lease claim --paths README.md` exits 1 naming L4. The worker's late commit then lands on its branch. Only after that, `dish D3 --state dropped --stopped r1` releases L4, `log.tsv` records `r1`, and the sibling's same claim returns a new lease.
- **Late command test.** It runs the opposite order. The wait reports a terminal run first, while a command the old worker started is still paused. A process standing in for that worker pauses before its last commit. `dish D3 --state dropped --stopped r1` releases L4, and the sibling's claim on `README.md` returns L5. Only then is the process released. It commits on `docs/d3` and runs `land.py submit --holder docs/D3 --branch docs/d3 --sha <its sha> --lease L4`, which exits 1 with the literal `not an active lease` message. `land.py status --holder docs/D3` prints nothing, `lease list` shows L5 alone on `README.md`, and the sibling's `fire` on those paths still succeeds.
- **Owner fence test.** Each process stands in for a command a replaced coordinator thread started, with `--owner t1@1`, and pauses after parsing and before it takes the store lock. `set --thread t2 --replace` records `t2@2` and raises the `docs/` floor to 2. Released one at a time, a `ticket add`, a `dish D3 --state dropped --stopped r1`, a `land.py lease release L4 --owner docs/@1`, and a `land.py lease renew L4 --owner docs/@1` on an expired L4 each exit 1 with the literal stale-owner message. `rail.tsv`, `log.tsv`, and `restaurant.json` are byte-identical to their state after the replacement, and L4's row in the landing database is unchanged. The same commands with `--owner t2@2` succeed. A rerun of `land.py owner --prefix docs/ --generation 2` changes nothing, and `--generation 1` exits 1.
- **Fresh-child test.** A fresh-child test per the `pstack-author-skill` skill gives a child acting as a coordinator an interrupt result of `status: "interrupt_requested"` and then a wait result of `timedOut: true`. It must not run `dish --state dropped` or `lease renew`, and must wait again on its next turn. Given a write that exits with the stale-owner message, it must run no further command in that turn.

### Change 7. One landing mode, one view per repository

Closes gaps 6 and 8.

- **Subtract.** Delete `set --landing` and the `--landing` flag of `open`. New `restaurant.json` files have no `landing` field, and an old field is ignored. The opener still asks the user for the mode, and passes it to `land.py init` or `land.py mode` as step 5 already does. The four tests that pass `--landing` move to the new form. Every doc line that shows the removed flags changes in this same change, per change 1's rule for removed names. That covers the brigade skill, `docs/guide.md`, and `docs/brigade-plan.md`.
- **`status`** prints the contract's mode, read from the first word of `land.py status`, as in `reporting: milestones, lands by merge, waiting tickets: 2`. With no contract it prints `no landing contract`.
- **`walk` groups by repository.** One header per `projectRoot` carries the `land.py status` line, followed by each coordinator's line without the old `lands by` field, its unreleased leases from `land.py lease list` matched by holder, and its blocked ticket count:

  ```
  ~/Projects/app: merge mode onto refs/remotes/origin/main. awaiting-merge: 1, landed: 40, leases held: 3, changes in flight: 3 of 4.
    docs (reports digest): in progress: 1, waiting to land: 1
      thread <id>, leases L41 (D7)
    engine (reports milestones): in progress: 2, waiting tickets: 1 (1 blocked)
      thread <id>, leases L42 (D12), L43 (D13)
  ```

  `walk --repo <root>` prints one repository.
- **Skill.** In Open steps 3 and 5, when the contract already has another mode, run `land.py mode`, which names the holders of unreleased leases, then tell each sibling with `t3_thread_send`, using the threads `walk --repo` prints. Standing orders do not restate the landing mode. A coordinator whose standing orders already state it deletes that rule on its next service. pstack-t3's rule 3 is one. The skill's section that describes `walk` for the user covers the grouped form.
- **User docs.** `docs/guide.md` gains a "Several coordinators on one repository" section covering changes 1 to 7: the caps, intake ownership, handoff, blocked tickets, lease renewal, and the grouped `walk`. Change 11 adds the admin to it.
- **Files.** Same as change 3, plus `docs/guide.md` and `docs/brigade-plan.md`.
- **Tests.** `status` and `walk` print the contract mode after `land.py mode` changes it, with no brigade command run in between. `walk` groups two siblings under one header and a third coordinator under another, with the literal lines. `set --landing` exits 2.

### Change 8. Reservations, shares, and contests in `land.py`

Adds the script mechanisms that carry out the admin's rulings. Work on it starts only after the [live two-coordinator run](#live-two-coordinator-run) of changes 1 to 7 has recorded its numbers. It edits the same files as changes 2 and 6.

- **`lease reserve --for <holder prefix> --paths <paths> --ruling R<n> [--ttl-hours 2]`** prints `S<n>`. Reservations live in a new `reservation` table, because the `lease` table's state check cannot be altered in place. Every admission, `lease claim` and the re-admission in `lease renew`, refuses another holder's overlap with a standing reservation, with `paths reserved for docs/ by ruling R4 until <time>`. A reservation arms, which starts its clock, at the first admission check that finds no other holder's live lease overlapping and room for one more change under the cap and the reserved prefix's share. Arming is an admission in the claim transaction, oldest reservation first. An armed reservation counts toward the cap and the share as one change in flight until the winner holds a lease taken from it. A claim by a holder under the reserved prefix removes the paths it covers from the reservation, and the reservation ends when none remain. A second `reserve` with the same ruling returns the same `S<n>`, or refuses with `S<n> for ruling R4 expired` once it has. A reservation that overlaps another standing reservation is refused. `lease unreserve S<n>` lifts one. `lease list` and `lease check` show them.
- **`land.py share --for <holder prefix> <n>`** sets that prefix's share of the cap. Admission refuses a claim that would put the prefix over its share, with `docs/ is at its share: 2 of 2`. It refuses shares that add up to more than the cap. `share --for <prefix> 0 --clear` removes a share. A prefix with no share is limited only by the cap.
- **`land.py contest --holders <a>,<b>`** opens a contest and prints `C<n>`. It refuses when either holder has an entry that is `landing`, `awaiting-merge`, or `landed`. A `bounced` entry is history and does not count, so an item resubmitted after a bounce can still be contested. While a contest is open, `land` leaves every entry of both holders out of every batch and, in `human` and `merge` mode, out of PR opening. **`land.py contest --settle C<n> --first <holder>`** turns the hold into an order. `land` then holds the other holder's entries until an entry of the first holder lands. Settling again replaces the order while neither has landed. `--settle` refuses an order that would close a cycle with another settled contest. **`land.py contest --cancel C<n>`** removes the hold or the order, for a conflict that turned out not to exist, an item that was dropped, or an overrule that orders nothing. Contests live in a new `contest` table, and both commands take the queue lock, so they never race a `land` run.
- **Every ruling write checks its owner.** `lease reserve`, `lease unreserve`, `share`, and every form of `contest` take `--owner <prefix>@<generation>` and check it against change 6's floor inside their own transaction. The admin passes `--owner .admin/@<generation>`, and a coordinator opening a contest passes its own `<slug>/@<generation>`. An enforcement command the admin's old run started, finishing after a recovery raised the `.admin/` floor, exits 1 with the stale-owner message and changes nothing. So a stale `share`, reservation, or settle can never act after a newer ruling or a user's overrule.
- **Files.** `t3/added/landing/scripts/land.py`, `t3/added/landing/SKILL.md`, `tests/test_landing.py`, generated `skills/landing/`, its fragment.
- **Tests.** A reservation for `docs/` refuses `engine/D3`'s overlapping claim with the literal message, and refuses the re-admission of `engine`'s expired lease on those paths. It admits `docs/D7`'s claim. A claim covering one of two reserved paths leaves the other reserved, and the winner's work counts once toward the cap. The clock does not start while another holder's live lease overlaps. With a cap of 1, two reservations waiting behind one lease arm one at a time, oldest first. Two processes claiming reserved paths at once, one from each coordinator, leave only the winner's lease. `share` refuses a sum over the cap, and admission refuses a claim over a share. While a contest is open, entries of both holders stay queued through a `land` run in each mode, including one submitted after the contest opened. After `--settle --first docs/D7`, the other holder's entry stays queued until `docs/D7` lands, including after `docs/D7` bounces and resubmits. Settling again in reverse works, and an order that closes a cycle is refused. Paused `share`, `lease reserve`, and `contest --settle` commands with `--owner .admin/@1`, released after `land.py owner --prefix .admin/ --generation 2`, each exit 1 with the literal stale-owner message, and the shares, reservations, and contest order are unchanged.

### Change 9. The executive admin's store and commands

Adds the code the admin needs, for one repository. It reuses intake ownership, `ticket move`, and the locked append (change 4), and the grouped `walk` (change 7). It edits only brigade files and calls no new `land.py` command, so it can run beside change 8. Change 10, which carries rulings out, needs both.

- **`open --admin --project-root <root>`.** It takes no `--name`. It claims `<store>/<project>/.admin/` with change 3's `mkdir`, so two opens at once produce one store and one `opened`. When `.admin` already names another `projectRoot`, it refuses with change 3's message. It writes `role: "admin"` and the root into `restaurant.json`. The admin is then a sibling of every coordinator on that root.
- **Intake and handoff need no new commands.** The admin is a sibling, so change 4's ownership check counts its `intake` list, and change 4's `ticket move` reaches it and leaves it. Its tickets carry plain sources and refs, because they all belong to one repository.
- **The admin store refuses work commands.** `fire`, `brief`, `dish`, `pass`, and `watch` exit 1 with `brigade: the executive admin routes work and never runs it`. `ticket add`, `ticket move`, `ticket take`, `86`, `request`, `rule`, `sync`, `status`, `close`, and `set` work.
- **`ticket add --request <id>`** records the request id with the ticket and refuses a second ticket for that id.
- **`request --to <coordinator> "<line>"`** in the admin store appends a `request` row to the admin's `log.tsv` with the next id `A<n>`, the target, and the line. Then it publishes `<coordinator dir>/inbox/A<n>.line` by writing a temporary file and renaming it, and prints the id and the coordinator's thread. **`request --republish`** reads each coordinator's `log.tsv` for its `inbox-done` rows, then takes the admin's lock and publishes again every `request` row whose file is absent and whose id has no such row. It never holds two stores' locks, so `inbox done` can finish a request between that read and the publish. A file whose id has an `inbox-done` row is therefore finished wherever it appears. `status` does not count it, and `inbox take` deletes it without printing it.
- **`inbox take`** files routed tickets as `ticket take` does, and prints each request file's id and line. **`inbox done <id>`** appends an `inbox-done` row to the coordinator's `log.tsv`, then deletes the request file. `ticket take` stays as the name for the ticket half. `status` adds `requests from the user: N` while request files wait.
- **`set --thread <id> --replace --expect <old>`** works only in the admin store. It replaces the recorded thread only when it is still `<old>`, under the store lock from change 4, and prints the schedule ids recorded at that moment. Like change 6's `--replace`, it adds 1 to `generation` and first raises the `.admin/` floor in the landing store. The claim also records the old thread as `previousThread`. Replacing a `recovering:` value also needs `--stopped <run id>`, `--stopped idle`, or `--stopped gone`, which it records in `log.tsv` as audit evidence. Without it, the command exits 1 with `brigade: the old run has not been confirmed stopped; wait for it with t3_thread_wait, then pass --stopped <run id>`, and the store stays `recovering:`. Every other write of the admin's `restaurant.json`, including the `lastActivityAt` update in `Restaurant.log` and the cursor updates in `sync` and `close`, rereads the file under the same lock and changes only its own fields. A write that read the file before a replacement can no longer restore the old thread. Every admin write checks change 6's owner token under the same lock, including `request`, `rule`, `sync`, `ticket move`, and the publish of a file into a coordinator's `inbox/`, which happens while the admin's lock is held. An ordinary coordinator keeps change 3's plain `--replace`, because its recovery is the user's request run from one thread. Compare-and-swap recovery for coordinators waits for a request that needs it.
- **`rule add --kind <kind> --parties <a,b> --question "..." --rule <rule> --decision "..." [--supersedes R<n>]`** records a ruling in `rulings.tsv` in the admin store and prints `R<n>`. **`rule overrule R<n> --decision "..."`** marks it `overruled` and records the user's ruling, which supersedes it. **`rule set R<n> --state done|expired`** records how a ruling ended. **`rule list [--state in-force]`** prints them. `rule` works only in the admin store. The admin's `close` lists the rulings recorded since its last update.
- **`set --reports-to <thread>`** records `reportsTo` in a coordinator's `restaurant.json`. `set --reports-to ""` clears it.
- **`status`** prints `thread <id>` first, or `thread not recorded`, so the fence step can compare it, and `reports to <thread>` when that is set.
- **`walk`** prints the admin's line first in its repository's group, by its `role`.
- **`sync`** in the admin store copies each coordinator's new `log.tsv` rows into the admin's own `log.tsv`, as `relay` rows whose note names the coordinator's store path and the row's byte offset. It reads from that coordinator's byte-offset cursor through `snapshot`, one reader that every `log.tsv` read in `brigade.py` uses, `rows` included.
  1. `snapshot` takes a shared `fcntl` lock on the source store's `restaurant.lock`. Writers hold the exclusive lock across tail repair and append (change 4), so neither runs during the copy. It reads every byte from the cursor to the end of the file into memory with unbuffered `os.read` calls, then releases the lock. A command that already holds its own store's exclusive lock reads under that lock and takes no second one.
  2. `sync` parses only the snapshot. It consumes only lines that end in a newline. An unfinished last line stays unread until its writer discards it or completes the row.
  3. It validates each line as change 4's `rows` does. At a malformed line it stops, leaves the cursor at that line's start, and prints `<store>/log.tsv at byte <n> is malformed; nothing past it relayed`, which the admin passes to the user as a failure.
  4. It skips any row the admin's log already holds a `relay` row for, so a crash between the copy and the cursor update copies nothing twice.
  5. Only after the source lock is released does it take the admin store's lock, check its owner token, write the `relay` rows, and set the cursor to the byte just past the last newline it consumed. It never holds two stores' locks at once, and a cursor always sits at a record boundary.

  The admin's service runs it in step 5. The admin's `close` reports its own log as any coordinator's does, with `relay` rows grouped by coordinator, and names each coordinator's newest file in `closeouts/`.
- **Files.** `t3/added/brigade/scripts/brigade.py`, `tests/test_brigade.py`, generated `skills/brigade/`, its fragment.
- **Tests for the store.** Two processes running `open --admin` at once print one `opened` and one `exists`, and leave one store. `open --admin` for a second root whose directory has the same name exits 1. `fire` in the admin store exits 1. A ticket moved from a coordinator to the admin and on to a sibling frees its ref at every step once the last ticket is `done`. So does a misroute moved back to the admin and on to a third coordinator. `rule add` then `rule overrule` leaves one `overruled` row and one `user` row, and the next `close` lists both.
- **Tests for requests.** A request file survives a failed send, and `inbox take` prints it until `inbox done`. A `request` killed after its row and before its file is published by `request --republish`, once. A request finished by `inbox done` while `request --republish` waits between its read and its publish is not counted or printed, and `inbox take` deletes its file. A `from-user` request replayed after its ticket was added files no second ticket.
- **Tests for sync.** A `sync` killed after its copy and before its cursor update copies nothing twice on the next run. `sync` copies a coordinator event appended while the previous `sync` ran, including a row whose timestamp is older than the previous one, exactly once. This extends change 4's kill-inside-append test to the relay. A `sync` run while the coordinator's `log.tsv` ends in the tail `<at><TAB>ticket<TAB>T6<TAB>waiting<TAB>fro` relays nothing for it, and its cursor stays at the tail's first byte. After the next `ticket take` recovers the handoff, `sync` relays exactly one row for it, whose note names the coordinator's store path and an offset equal to the old cursor, and whose copied fields are `ticket`, `T6`, `waiting`, and `from app/engine/T6`. A hand-written joined line stops `sync` with the literal malformed message and leaves the cursor at that line. The reader race test starts with `log.tsv` ending in the tail `2026-10-06T00:00:00Z<TAB>ticket<TAB>T6<TAB>waiting<TAB>fro`. A test hook limits `snapshot` to 16-byte reads and pauses `sync` after its first read past the cursor. A process then appends `2026-10-06T00:00:01Z<TAB>ticket<TAB>T7<TAB>waiting<TAB>from app/engine/T7<NEWLINE>` through `Restaurant.append`, which must repair the tail. One second later that append has not returned, because it waits for the lock. Released, `sync` relays nothing and leaves its cursor at the tail's first byte, and the append then finishes. The next `sync` relays exactly one row, with timestamp `2026-10-06T00:00:01Z`, id `T7`, and note `from app/engine/T7`. No `relay` row pairs `T6` with that note.
- **Tests for recovery.** Two processes running `set --thread --replace --expect` with the same old id leave one new thread and one exit 1. A `log` write that read `restaurant.json` before a replacement leaves the new thread recorded. `set --thread <new> --replace --expect recovering:<id>` without `--stopped` exits 1 with the literal message and leaves `recovering:<id>` recorded. `set --thread --expect` in an ordinary coordinator's store exits 1.
- **Tests for the owner fence.** Each test models an interrupt that returned `interrupt_requested` and old commands that finish later. Processes standing in for the old service's commands carry `--owner t1@1` and pause after its fence step, before they take the store lock.
  1. Claim first. The recovery's claim records `recovering:t9@2` and raises the `.admin/` floor to 2. The paused `rule add` is then released. It exits 1 with the literal stale-owner message, and `rulings.tsv`, `log.tsv`, and `restaurant.json` are byte-identical to their state after the claim. This is round 2's reproduction, now refused.
  2. Terminal wait first, then the stale commands. The wait reports run r1 terminal, `set --thread t2 --replace --expect recovering:t9 --stopped r1` records `t2@3`, and the new thread's first service runs. Only then are paused `rule add`, `request --to docs`, `sync`, `ticket move`, `land.py share`, `land.py lease reserve`, and `land.py contest --settle` released, each with the old token. Each exits 1 with its literal stale-owner message. `rulings.tsv`, the admin's `log.tsv` and cursors, `docs`'s `inbox/` and `rail.tsv`, and the shares, reservations, and contest order in the landing store are unchanged. So no command of the old run can authorize work after the replacement.
  3. A command that took the lock before the claim finishes its whole write. The claim waits for the lock and then succeeds, and the write's row in `log.tsv` comes before the claim's row.

### Change 10. The executive admin in the brigade skill

It follows changes 8 and 9.

The section this change added to the brigade skill now lives in the `brigade-admin` skill.

- **The admin's section.** A new section of the brigade skill, "Executive admin", with the opening steps, the services, the message tables, the ruling rules and escalation list, the never-do list, recovery and retirement, and the rules for what the user hears, from [The executive admin](#the-executive-admin). It covers one repository.
- **A coordinator's side.** A coordinator carries out a `ruling` for its own side and may `appeal`. When its item and another coordinator's would conflict in the queue, it runs `land.py contest` and then sends the `contest` line. It treats `from-user` as a message from the user and answers with `reply`. The liveness check sends the `blocked` line after an hour. Change 4's handoff message becomes the `ticket` line, with the handoff id as its `clientRequestId`.
- **Reporting through the admin.** Run a service step 9 gains the rule for a coordinator with `reportsTo`, including the fallback to replying directly when a send fails. First service gives every coordinator with `reportsTo` a schedule that runs a service at least hourly, whether or not it owns intake. Run a service step 2 begins with `inbox take`. The skill keeps the user in charge.
- **The plan document.** `docs/brigade-plan.md` gains a row for the executive admin. Its sentence that brigade has no overall coordinator gains that the admin serves the user on one repository, and rules on conflicts between coordinators by published rules that the user can overrule.
- **Files.** `t3/added/brigade/SKILL.md`, generated `skills/brigade/`, `docs/brigade-plan.md`, its fragment. If the skill's frontmatter description changes, `docs/skills.md` joins the lease, because the build regenerates it from descriptions.
- **Test.** This changes skill behavior, so it needs fresh-child tests per the `pstack-author-skill` skill, one per role. A child acting as a coordinator with `reportsTo` set, given a merge, must send the `merged` line with `mode: "queue"` and send the user nothing. Given a `ruling` line whose ruling is `superseded`, it must do nothing. A child acting as the admin, given a `decision` line, must not answer it. Given a block older than an hour where the user's priorities rank one side higher, it must record a ruling decided by `priority`, reserve the paths for that side, and send no question to the user. Given a block that no rule separates, it must escalate with a default. Given a recovery whose interrupt returned `interrupt_requested` and whose wait returned `timedOut: true`, it must launch no thread and leave the store `recovering:`. Given a `rule add` that exits with the stale-owner message, it must run no further command, including the ruling's `land.py` enforcement.

### Change 11. User docs for several coordinators

- **Content.** Change 7 already adds a "Several coordinators on one repository" section to `docs/guide.md`, covering the caps, intake ownership, handoff, blocked tickets, and the grouped `walk`, so users of changes 1 to 7 have it before the admin exists. This change adds the executive admin and its rulings to that section, and a row in `docs/how-it-works.md`. These two are the docs batches that change 1's rule asks for, so changes 2 to 6 and 8 to 10 leave these files alone.
- **Files.** `docs/guide.md`, `docs/how-it-works.md`, its fragment.
- **Test.** `python3 scripts/build.py` passes. Every command the section shows appears in a unit test from changes 2 to 9.

## Lease plan

| Change | Leased paths | Can run beside |
| --- | --- | --- |
| 1 | `CHANGELOG.md`, `CONTRIBUTING.md`, `tests/test_pstack_t3.py`, its fragment | 2, 3 |
| 2 | `t3/added/landing`, `skills/landing`, `tests/test_landing.py`, its fragment | 1, 3, 4, 5 |
| 3 | `t3/added/brigade`, `skills/brigade`, `tests/test_brigade.py`, its fragment | 1, 2 |
| 4 | same as 3, with its own fragment | 2 |
| 5 | same as 3, with its own fragment | 2 |
| 6 | same as 3, plus `t3/added/landing`, `skills/landing`, `tests/test_landing.py`, with its own fragment | none |
| 7 | same as 3, plus `docs/guide.md`, `docs/brigade-plan.md`, with its own fragment | none |
| | The live two-coordinator run of changes 1 to 7 | nothing starts until it records its numbers |
| 8 | same as 2, with its own fragment | 9 |
| 9 | same as 3, with its own fragment | 8 |
| 10 | `t3/added/brigade/SKILL.md`, `skills/brigade`, `docs/brigade-plan.md`, its fragment | none |
| 11 | `docs/guide.md`, `docs/how-it-works.md`, its fragment | none |

A fragment path is unique to its branch, so fragments never overlap. Changes 2 and 3 can run beside change 1 because they write a fragment and never touch `CHANGELOG.md`. If one lands first, its fragment waits in `changes/` for change 1's release step.

Changes 3 to 7 all edit `brigade.py`, the brigade skill, and its tests, so they land one after another. Splitting `brigade.py` into modules to allow parallel leases would cost more than the sequencing does. Change 2 lands early, because change 6's renewal depends on its safe renew. Change 6 also needs change 2's `status --holder`, and change 5's repository-cap line reads the count change 2 adds to `land.py status`, so 2 lands before 5 and 6.

The admin work waits for the live run. Changes 1 to 7 close every gap on their own, and the run shows whether they work before a new role is built on them. Change 8 edits `land.py` and the landing skill, and change 9 edits the brigade files, so the two can run side by side. Change 10 needs both, and change 11 documents change 10. A coordinator running this plan uses `fire --paths` with exactly the paths in this table.

## Live two-coordinator run

Run after change 7 lands, on a clone of `creedants/pstack-t3-sandbox`, the scratch repository the request for this design names for the live run. Changes 8 to 11 start only after its first part records its numbers. Opening issues there is still a GitHub write outside pstack-t3's own PR flow. The ref check compares strings, so the run uses an existing sandbox issue URL, or a made-up ref, rather than opening an issue.

The clone is not a git worktree of the sandbox's T3 project, so T3 refuses an `existing_worktree` strategy that points at it. Register the clone as its own T3 project with `t3_project_create`. Launch every coordinator and the admin in that project with `workspaceStrategy: {"type": "root"}`, as the brigade skill says. Workers then use the skill's `worktree` strategy unchanged.

1. `land.py init --trunk main --mode merge --merge-method <the method the repository allows> --cap 3 --check <the sandbox's test command>`. The sandbox allows only squash merges, so pass `--merge-method squash`. Open `core` with `--intake github`, and fill `core`'s `menu.md` before opening `docs`. Then open `docs`. Give each `--workers 2`. `docs`'s `open` prints `core`'s purpose and exclusions, and prints `purpose: not written yet` when `core`'s menu is still the template.
2. `docs` adds a ticket with `--source github` and is refused, naming `core`. `core` files the issue, and filing it again is refused.
3. `core` starts one item on `README.md` and one on `src/`. `docs`'s `fire` on `README.md` is refused. `docs`'s `watch` prints `waiting on L<n> (core/D1)`.
4. `docs` starts one item on a disjoint path, which makes 3 changes in flight. A third `fire` in `core` is refused by its own cap of 2. A second `fire` in `docs` is refused with the repository cap message, `3 of 3 changes in flight`.
5. `core`'s `README.md` item passes review from another model family, and `core` submits it and marks it `queued`. Then `docs`, not `core`, runs `land`, which opens the PR for `core`'s entry. `core`'s next liveness check prints `landed as E<n>` or `awaiting merge`, and `core` watches its own PR.
6. Within one liveness interval after `core`'s `README.md` lease is released, `docs`'s `watch` prints the `unblocked` line, and `docs` runs that `fire`.
7. `core` moves a ticket to `docs`. `docs` wakes on the message, and `ticket take` files it once.
8. `land.py mode human` while an entry is queued is refused. When idle it names the holders of unreleased leases, and `walk` shows one mode for both coordinators.
9. `core` drops its `src/` item while its worker runs. It calls `t3_thread_interrupt`, waits with `t3_thread_wait` until the run reports a terminal state, and only then runs `dish --state dropped --stopped <run id>`. A `docs` claim on those paths is refused until that command runs, and succeeds after it.

Record four numbers.

- Duplicate tickets filed. The target is 0.
- Items left `queued` after they landed. The target is 0.
- Minutes from a lease release to the retry. The target is at most one liveness interval, 10 minutes at `milestones`.
- `fire` refusals, counted by kind (`lease`, `repository`, `workers`).

After change 10 lands, the same run continues with an executive admin.

1. `core` drops `github` from its intake. Open the admin with `open --admin --project-root <sandbox root>`, give it `--intake github`, launch its thread in the clone's T3 project, and have `core` and `docs` run `set --reports-to <its thread>`.
2. The user sends one request to the admin. It files the request with `ticket add --source user`, moves the ticket to `docs`, and sends the `ticket` line, and `docs` takes it.
3. When `docs`'s item merges, `docs` sends the `merged` line and sends the user nothing. The admin replies at the user's level, in plain language.
4. With `## Priorities` empty, `core` and `docs` both wait for `CONTRIBUTING.md` past an hour, while a third item holds it. Use a path neither purpose names. Each coordinator lists its sibling's purpose under `## Off the menu`, so a path one purpose names, such as `README.md` for a docs coordinator, is decided by `purpose` and never reaches age. Shorten the threshold for the run if no conflict lasts that long. The admin rules by age, records the ruling, and reserves the paths for the older side. When the lease frees, the other side's `fire` is refused with the reservation message, and the winner's succeeds. `lease list` shows no lease taken away.
5. The user overrules that ruling in plain words. The admin records the overrule, lifts the reservation, and reserves for the other side. Its next update lists both rulings.
6. `docs` finds that its passed item depends on one of `core`'s, opens a contest, sends the `contest` line, and then submits the item rather than holding it. Neither item lands until the admin settles it by dependency, and then `land` lands `core`'s item first.

That part records three more numbers.

- Replies to the user from coordinator threads that the user did not write to first. The target is 0 while sends deliver. A failed send expects the coordinator's direct reply instead, and the run checks that case once by sending to a thread id that does not exist.
- Rulings made, by kind and by deciding rule.
- Escalations, each with the reason the rules could not settle it.

## Out of scope

- **A machine-wide worker cap across repositories.** The governor already caps builds and tests machine-wide. [capacity.md](capacity.md) measured 40 idle agents on this machine with 5.9 GiB of memory still free. The sum of per-repository caps is the machine budget the user picks.
- **Coordination between repositories.** Coordinators on different repositories share no leases, queue, or intake. The first admin serves one repository. An admin that spans repositories or T3 projects needs repository-qualified intake, cross-project routing, and a live test of `t3_thread_send` across projects, so it is a later change.
- **Compare-and-swap recovery for ordinary coordinators.** Only the admin's store gets `set --thread --expect` and the `--stopped` requirement on `set --thread`. A coordinator keeps atomic opening and change 3's refusal to replace a recorded thread without `--replace`. It still uses `dish --stopped` to drop an item, and change 6's owner token fences its writes.
- **A record of message sends.** Messages are wakes. Events and requests already have durable identities, a `log.tsv` position and a request id, so no sent or delivered rows are kept.
- **Siblings matched across worktrees.** Siblings match by `projectRoot` string. Two coordinators on one repository opened with different checkouts are not siblings. Matching by git common directory, as `land.py` does, can come later if anyone opens coordinators that way.
- **Leases finer than a path.** No line or section leases.
- **Starting work automatically when a lease frees.** `watch` reports it, and the coordinator decides.
- **Priority decided by the scripts.** The scripts enforce the cap, shares, reservations, and contest holds, but they decide nothing. The admin decides by its rules, and the user sets the priorities those rules read.
- **The one-hour threshold for a `blocked` line** is a starting guess. The live run should show whether it is too slow or too noisy.
- **A `lease widen` command.** `submit`'s error says "widen the lease", and no command does that. This affects one coordinator as much as several, so it belongs in its own change.

## The experiment script

This is the audit script, run against commit `5794d40`. It records what each command printed and asserts nothing. The tests in changes 2 to 7 are the asserting checks. Run it with the `skills/` directory of a checkout at `5794d40`, for example one made with `git worktree add /tmp/pstack-t3-5794d40 5794d40`, as `two_restaurants.sh /tmp/pstack-t3-5794d40/skills`. Never point it at a current `skills/` directory. After change 7, its `--landing` flags no longer parse. It writes only under a fresh `mktemp -d` and prints that path at the end.

```bash
#!/usr/bin/env bash
# Two coordinators on one scratch repository. Usage: two_restaurants.sh <skills dir>
set -u
SK=$1
T=$(mktemp -d)
export XDG_STATE_HOME=$T/state BRIGADE_STORE=$T/brigade
B="python3 $SK/brigade/scripts/brigade.py"
L="python3 $SK/landing/scripts/land.py --repo $T/app"
step() { printf '\n## %s\n' "$*"; }
run() { printf '$ %s\n' "${*/$T/\$T}"; "$@" 2>&1 | sed "s#$T#\$T#g"; printf '[exit %s]\n' "${PIPESTATUS[0]}"; }

git init -q --bare -b main $T/origin.git
git clone -q $T/origin.git $T/app 2>/dev/null
cd $T/app
git config user.email s@x; git config user.name s
mkdir -p docs src; for f in CHANGELOG.md README.md docs/guide.md src/a.py src/b.py src/c.py src/d.py; do echo x > $f; done
git add -A; git commit -qm init; git push -q origin main

step "contract and two coordinators"
run $L init --trunk main --mode push --check true
run $B open --project-root $T/app --name docs --landing push
run $B open --project-root $T/app --name engine --landing push
A="$B --at $BRIGADE_STORE/app/docs"; E="$B --at $BRIGADE_STORE/app/engine"
for r in docs engine; do sed -i "s/^What this restaurant exists.*/Purpose of $r: keep the app healthy./" $BRIGADE_STORE/app/$r/menu.md; done

step "gap 1: same --ref in both, and twice in one"
run $A ticket add --summary "issue 7" --source github --ref https://github.com/o/r/issues/7
run $E ticket add --summary "issue 7" --source github --ref https://github.com/o/r/issues/7
run $E ticket add --summary "issue 7 again" --source github --ref https://github.com/o/r/issues/7

step "gap 5: overlapping fire across coordinators"
run $A fire --tickets T1 --station feature --summary "docs change" --paths CHANGELOG.md,docs/guide.md
run $E fire --tickets T1 --station bug-fix --summary "engine fix" --paths src/a.py,CHANGELOG.md
run $E ticket list --state waiting
run $E status
run $L lease list

step "gap 2: no cap on work in progress"
for n in 4 5 6 7; do $E ticket add --summary "t$n" >/dev/null; done
run $E fire --tickets T2 --station feature --summary one --paths src/b.py
run $E fire --tickets T3 --station feature --summary two --paths src/c.py
run $E fire --tickets T4 --station feature --summary three --paths src/d.py
run $E fire --tickets T5 --station feature --summary four --paths src/e.py
run $E status; run $A status

step "gap 6: set --landing in one coordinator, then land.py mode"
run $A set --landing merge
run $L status
run grep -H '"landing"' $BRIGADE_STORE/app/docs/restaurant.json $BRIGADE_STORE/app/engine/restaurant.json
run $L mode human
run grep -H '"landing"' $BRIGADE_STORE/app/docs/restaurant.json $BRIGADE_STORE/app/engine/restaurant.json
run $L mode push

step "gap 9: one coordinator's land run lands the other's entry"
git checkout -q -b engine/d1 && echo y >> src/b.py && git commit -qam "engine b" && ESHA=$(git rev-parse HEAD) && git checkout -q main
git checkout -q -b docs/d1 && echo y >> CHANGELOG.md && git commit -qam "docs changelog" && DSHA=$(git rev-parse HEAD) && git checkout -q main
run $L submit --holder engine/D1 --branch engine/d1 --sha $ESHA --lease L2 --reviewer x/y
run $L submit --holder docs/D1 --branch docs/d1 --sha $DSHA --lease L1 --reviewer x/y
run $L land
run $L land
run $L status

step "land.py mode with a sibling's entry queued"
git checkout -q -b engine/d2 && echo y >> src/c.py && git commit -qam "engine c" && CSHA=$(git rev-parse HEAD) && git checkout -q main
run $L submit --holder engine/D2 --branch engine/d2 --sha $CSHA --lease L3 --reviewer x/y
run $L mode human

step "gaps 10 and 12: an expired lease, a sibling's claim, submit and renew"
run $L lease claim --holder docs/D9 --paths README.md --ttl-hours 0.0003
sleep 2
run $L lease claim --holder engine/D9 --paths README.md
git checkout -q -b docs/d9 && echo y >> README.md && git commit -qam "docs readme" && RSHA=$(git rev-parse HEAD) && git checkout -q main
run $L submit --holder docs/D9 --branch docs/d9 --sha $RSHA --lease L6 --reviewer x/y
run $L lease renew L6
run $L lease list

step "gap 11: another repository with the same directory name"
mkdir -p $T/other && git init -q -b main $T/other/app
run $B open --project-root $T/other/app --name docs --landing local
run grep projectRoot $BRIGADE_STORE/app/docs/restaurant.json

step "gap 3: no command moves a ticket"
run $E ticket move T6 --to docs

step "gap 4: a third coordinator says nothing about siblings"
run $B open --project-root $T/app --name release --landing push

step "gap 8: walk"
run $B walk
echo; echo "scratch: $T"
```
