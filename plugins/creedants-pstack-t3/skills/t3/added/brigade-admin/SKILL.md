---
name: brigade-admin
description: "Run the executive admin for the brigade coordinators on one repository. It is one pinned T3 thread that forwards the user's requests, files shared intake once, rules on conflicts between coordinators by published rules the user can overrule, and writes one plain-language update. Use for 'executive admin', 'open an executive admin', 'an admin over the coordinators on one repository', 'recover the executive admin', 'retire the executive admin', or running that thread. For one coordinator on a project or focus area, use brigade."
---

# Brigade admin

The executive admin is one thread that works for the user on one repository. As an assistant, it keeps the user up to date across every coordinator there, forwards requests, files shared intake once, and writes one plain-language update. As a coordinator of coordinators, it settles conflicts between them on its own authority, by the rules in [Rulings](#rulings), and logs every ruling so the user can review and overrule it. It escalates only what the rules cannot settle. The scripts enforce. The cap stays in `land.py`, paths stay exclusive through leases, and each ruling is carried out by a script. The user sets the rules' inputs, answers every decision, and has the last word. Each coordinator keeps its own work, reviews, queue entries, and `menu.md`. Without an admin, every coordinator works as [the brigade skill](../brigade/SKILL.md) says.

Its store is `<store>/<project>/.admin/`, beside the coordinators it serves, with `role: "admin"` in `restaurant.json`. It is a sibling of each of them, so intake ownership, `ticket move`, and handoff ids work as for any sibling. `<store>` is the store root. Without `--store`, it is `$BRIGADE_STORE` when it is set and not empty, else `$XDG_STATE_HOME/pstack-t3/brigade`, and `$XDG_STATE_HOME` defaults to `~/.local/state` when it is unset or empty. `<root>` is the repository's project root. `<project>` is the last component of `<root>` after symlinks resolve, lowercased, with each run of characters outside `a-z0-9` replaced by `-` and any leading or trailing `-` removed. An admin thread follows this skill, and [Filing tracker work](../brigade/SKILL.md#filing-tracker-work) and [Digest messages](../brigade/SKILL.md#digest-messages) in the brigade skill. That skill's [Open a restaurant](../brigade/SKILL.md#open-a-restaurant), [First service](../brigade/SKILL.md#first-service), [Run a service](../brigade/SKILL.md#run-a-service), [Liveness check](../brigade/SKILL.md#liveness-check), and [Git and PR housekeeping](../brigade/SKILL.md#git-and-pr-housekeeping) are for coordinators. The admin runs the brigade skill's script, [`../brigade/scripts/brigade.py`](../brigade/scripts/brigade.py) from this file, so `<skills>` is the directory that holds both skills. Read that skill's [Terms](../brigade/SKILL.md#terms), [The script](../brigade/SKILL.md#the-script), and [Reporting to an executive admin](../brigade/SKILL.md#reporting-to-an-executive-admin) sections before the first command. The first two define the store's files, `$L`, the owner token, and each command the block below does not list. The third holds the coordinator's side of each line and each ruling. Here `$B` is `python3 <skills>/brigade/scripts/brigade.py --at <store>/<project>/.admin --owner <thread>@<generation>`. Drop `--owner` on `set --thread`, per [The script](../brigade/SKILL.md#the-script). Opening step 4 runs before any thread is recorded, so it also drops `--owner`.

```bash
python3 <skills>/brigade/scripts/brigade.py open --admin --project-root <root> --reporting <level>   # opened or exists, then every coordinator on the root
$B request --to <coordinator> "<line>"     # records A<n>, publishes it into that inbox, prints the thread to tell
$B request --republish                     # publishes again any request a crash left unwritten that its coordinator has not finished
$B rule add --kind contested-paths|ownership|shares|queue-order --parties <a>,<b> --question "..." --rule purpose|priority|age|related-work|dependency|floor|user --decision "..." [--supersedes R<n>]   # prints R<n>
$B rule overrule R<n> --decision "<the user's words>"   # marks it overruled and records the user's ruling
$B rule set R<n> --state done|expired ; $B rule list [--state in-force]
$B sync                                    # copies each coordinator's new log.tsv rows into this log, or prints nothing new
$B set --thread <new> --replace --expect <old> [--stopped <run id>|idle|gone]   # compare-and-swap of the admin's thread
```

The admin store refuses `fire`, `brief`, `dish`, `pass`, and `watch` with `brigade: the executive admin routes work and never runs it`.

## Open an executive admin

The user asks any thread for an executive admin.

1. Ask the user for the reporting level with the host's question tool, unless the user already said it. Recommend `digest`, because the admin exists so the user hears less.
2. Run `python3 <skills>/brigade/scripts/brigade.py open --admin --project-root <root> --reporting <level>`. It prints `opened <dir>` or `exists <dir>`, then one block per coordinator on the root with its purpose. Only the caller that got `opened` launches a thread.
3. Write the user's priorities under `## Priorities` in its `menu.md`, highest first, with the user. Add which intake sources it should own. Without priorities, the rules fall back to purposes and age.
4. Move shared intake. Each coordinator that lists the shared source runs `set --intake <its other sources>`, or `set --intake ""` when that source was its only one. [The script](../brigade/SKILL.md#the-script) says when that is refused. To clear a refusal, the coordinator finishes that source's tickets or moves them to the admin with `ticket move <id> --to .admin`. Then run `python3 <skills>/brigade/scripts/brigade.py --at <store>/<project>/.admin set --intake <source>` with no `--owner`. The admin has no thread until step 5, so no owner token exists yet. [The script](../brigade/SKILL.md#the-script) says which writes need one after step 5.
5. Launch the thread with `t3_thread_launch` in the repository's T3 project, with `workspaceStrategy: {"type": "root"}`, title `Executive admin`, and the message "Use the brigade-admin skill. You are the executive admin for the store at `<store>/<project>/.admin`. Wait for the start message." Record it with `$B set --thread <id>`. Then send it "Run your first service." with `t3_thread_send` and mode `"auto"`.

When the user asks the admin to open a coordinator, it runs [Open a restaurant](../brigade/SKILL.md#open-a-restaurant) in the brigade skill, shows the user any overlap with the purposes `open` printed, and launches the new thread once the user agrees.

## Admin first service

1. `t3_thread_organize` with `action: "pin"` and no `threadId`.
2. Create three schedules with `schedule_task`, bound to this thread, and record each under the name its bullet gives with `$B set --schedule <name>=<id>`. Each prompt says "Use the brigade-admin skill. You are the executive admin for the store at `<store>/<project>/.admin`. Reporting level: `<level>`. Run a service."
   - `intake`: `{"type": "interval", "everyMs": 3600000}`. Each service also runs the idle check, which must run well inside the 6-hour lease expiry.
   - `morning`: `{"type": "fixed_time", "timeOfDay": "09:00"}`, for routing and checks.
   - `evening`: `{"type": "fixed_time", "timeOfDay": "18:30"}`, after the coordinators' 18:00 reports. The prompt adds "Write the update."
   It creates no liveness or drain schedule, because it runs no workers and owns no queue entries.
3. Send each coordinator the `reports-to` line as a request, per Admin messages, with this thread's id as `<thread>`.
4. Run an admin service.

## Admin service

Every wake runs one service, whether a schedule, a message, or a user message.

1. Run `$B status`. [The script](../brigade/SKILL.md#the-script) describes its `thread` line and its `owner` token. When it names another thread, or prints `thread not recorded` because the admin was retired, end the turn with no action. Otherwise pass that token as `--owner` on every `$B` command, and `--owner .admin/@<generation>` on every `$L` ruling write, which is `lease reserve`, `lease unreserve`, `share`, and `contest`. `$L lease list`, `$L status`, and `$L land` take no `--owner`, and the admin never runs `land`. A write refused with `is stale` means another thread owns the store. End the service at once and run no further command, including the ruling's `$L` enforcement.
2. Read `menu.md`, `$B status`, `$B 86 list`, and `python3 <skills>/brigade/scripts/brigade.py walk --repo <root> --stale-hours 3`. When the user's message answers a question `$B 86 list` prints, run `$B 86 answer Q<n> --answer "<the user's words>"` before anything else, then act on it per [Escalate](#rulings).
3. `$B inbox take`, for tickets moved back. Then file each piece of work the user asks for in this service as `$B ticket add --summary "<the user's request>" --source user`, one ticket per request, with the `--ref` that [Filing tracker work](../brigade/SKILL.md#filing-tracker-work) gives it. That section's Refusals step says what a refused add means. Run that section's Match step for each request before its add, even when it names no ref. Route it per step 4 like any other ticket. A message that settles a conflict between coordinators, such as which one's item lands first, is a ruling per [The user's ruling](#rulings), not a ticket. Then intake from its owned sources with `$B ticket add --summary "..." --source <source> --ref <ref>`, reading each source and filing each finding per [Filing tracker work](../brigade/SKILL.md#filing-tracker-work). [The script](../brigade/SKILL.md#the-script) says what `ticket move` in step 4 does with that ref. Then `$B request --republish`.
4. Route each waiting ticket to the coordinator whose purpose fits with `$B ticket move <id> --to <coordinator>`, then `t3_thread_send` to the thread it prints, with mode `"auto"`, the `ticket` line from Admin messages, and the handoff id `<project>/.admin/T<n>` as `clientRequestId`. A ticket that fits two purposes gets an ownership ruling. A ticket no purpose fits becomes `$B 86 add` with options and a default.
5. Read coordinator events from two sources. Run `$B sync`. It prints each coordinator's new store rows. The event table in [Reporting to an executive admin](../brigade/SKILL.md#reporting-to-an-executive-admin) says which lines leave a store row and which are message-only. A message-only line never appears in `sync`. Act on each one from the message that woke this service. Rule on each conflict either source shows, such as a block older than an hour, a `contest` or `appeal` line, or waiting work that needs a changed share, per [Rulings](#rulings). Record each ruling with `$B rule add` before carrying it out. Then reconcile every ruling `$B rule list --state in-force` prints, mark the ones whose condition ended with `$B rule set`, and carry out the rest again, which repeats nothing. Pass each coordinator's `decision` to the user. Never answer it. When the wake message is a coordinator's `reply` line, pass it to the user, including a decline and its reason, per [What the user hears from the admin](#what-the-user-hears-from-the-admin). A malformed-line failure from `sync` goes to the user as a failure.
6. When the repository sits at its cap while tickets wait for an hour, park a decision proposing a new cap, with a default. A coordinator that `walk` marks idle while it holds leases becomes a decision for the user, before its 6-hour leases lapse.
7. Reply per [What the user hears from the admin](#what-the-user-hears-from-the-admin).

## Admin messages

Every exchange is an explicit `t3_thread_send`. The admin sends with mode `"auto"`, so the coordinator wakes. Coordinators send the event lines as [Reporting to an executive admin](../brigade/SKILL.md#reporting-to-an-executive-admin) says. Messages are wakes, and the stores are the record for every line with a store row. The admin reads those events through `sync`, which reads each `log.tsv` past a cursor and relays each row once, so a second wake for one stored event finds nothing new. It reads a message-only line from the message itself and acts on it in that service, per service step 5.

Every admin line except a routed ticket is a request. Run `$B request --to <coordinator> "<line>"`. It prints `A<n> for <coordinator>; tell thread <id>`. When its output ends with `no thread recorded for <coordinator>` instead of `tell thread <id>`, send nothing. The request waits in that inbox. Otherwise call `t3_thread_send` to that thread with the line and `clientRequestId` `A<n>`, so a retried send delivers once. Retry a failed send with the same `A<n>`, or leave it to the next scheduled wake, because the file waits in the inbox. Never run `request` again to retry. Each run records a new id, so the coordinator would act twice.

The exact text of each line is in [Reporting to an executive admin](../brigade/SKILL.md#reporting-to-an-executive-admin), under Requests. The table there holds four of them, and the sentence after it holds the `ticket` line. Copy the line from there and fill in its fields. This skill's `<coordinator>`, the directory name of the coordinator the line goes to, fills the `<restaurant>` field.

| Line | Sent when |
| --- | --- |
| `ticket` | it routes a ticket, as in service step 4 |
| `from-user` | the user's words are meant for that one coordinator: a question about its work, a mode change, or a disagreement with its verdict. Work the user asks for is a ticket per service step 3, and a conflict between coordinators the user settles is a ruling, never a `from-user` line. Quote the user's words |
| `answer` | the user answers that coordinator's decision, including an answer that keeps it parked. Send the option the user picked word for word, or the user's words when they picked none. What the coordinator does with it is in [Reporting to an executive admin](../brigade/SKILL.md#reporting-to-an-executive-admin), under Requests. |
| `reports-to` | its first service, recovery, or retirement. `<thread>` is this thread's id, or `none` on retirement |
| `ruling` | it records a ruling. Send it to each coordinator involved |

## Rulings

The admin rules on four kinds of conflict between coordinators. It applies the rules in order, and the first rule that separates the parties decides. A ruling stands until it is done, expires, is superseded, or the user overrules it. How a coordinator complies is in [Reporting to an executive admin](../brigade/SKILL.md#reporting-to-an-executive-admin), under A ruling's side.

The rules read three inputs. Each coordinator's `menu.md`, with its purpose and `## Off the menu`. The user's priorities, the ranked names under `## Priorities` in the admin's `menu.md`. A coordinator the list does not name ranks below every named one, level with the other unnamed ones. Only the user changes the list. Age, how long the waiting work has waited. A blocked ticket's age counts from its first `blocked` row. A coordinator's age is its oldest waiting ticket's. Queue order counts from the `contest` line.

| Kind | Question | Rules, in order |
| --- | --- | --- |
| `contested-paths` | Which coordinator claims a contested path next, including a hot shared file such as `README.md` | 1. A path one purpose names and the other's `## Off the menu` excludes goes to the first (`purpose`). 2. The user's priorities (`priority`). 3. The older waiting work (`age`). |
| `ownership` | Which coordinator owns a request that fits two purposes | 1. A coordinator whose `## Off the menu` excludes it loses (`purpose`). 2. The user's priorities (`priority`). 3. The coordinator whose open work already touches the request's paths or ref (`related-work`). 4. Otherwise escalate. |
| `shares` | How many of the repository's changes in flight each coordinator may hold, out of the cap | 1. Each coordinator with waiting work gets one, by priorities, then age, until the cap runs out (`floor`). 2. The rest go by priorities, highest first, up to each coordinator's waiting work (`priority`). 3. A tie goes to the older waiting work (`age`). |
| `queue-order` | Which of two coordinators' passed items lands first when one would break or conflict with the other | 1. An item the other depends on, as a `contest` line stated, lands first (`dependency`). 2. The user's priorities (`priority`). 3. The older `contest` side (`age`). |

Age decides only when the earlier rules leave the parties level. Different ages then decide by `age`. Equal ages tie at the age rule. When priorities rank one side higher, the ruling is `priority` even when the ages are equal, because priority comes before age. The admin escalates only when no rule separates the parties. So every ruling has one outcome or escalates.

A live lease is never taken away. A contested-path ruling decides who claims next when the lease frees. What each side then does is in [Reporting to an executive admin](../brigade/SKILL.md#reporting-to-an-executive-admin), under A ruling's side. A share counts changes in flight, as the cap does. Shrinking a share stops no running work.

**The user's ruling.** When the user settles a conflict between coordinators that no ruling covers, such as an order for two items, record it with `$B rule add --kind <kind> --parties <a>,<b> --question "..." --rule user --decision "<the user's words>"`. Then carry it out and send the `ruling` lines like any other ruling.

Carry out each ruling with its script, after `$B rule add` recorded it.

- `contested-paths`: `$L lease reserve --for <winner>/ --paths <paths> --ruling R<n> --owner .admin/@<generation>`. It prints `S<n>`. Every other holder's claim on those paths is refused until the winner claims them or the reservation expires. It arms, and starts its 2-hour clock, once no other holder's live lease overlaps it and both the cap and the winner's share have room for one more change. A reservation for a winner whose share is 0 stays waiting, so that winner also needs a shares ruling.
- `ownership`: `$B ticket move <id> --to <winner>` when the admin holds the ticket. Otherwise the holder acts on the `ruling` line as [Reporting to an executive admin](../brigade/SKILL.md#reporting-to-an-executive-admin) says, under A ruling's side.
- `shares`: `$L share --for <coordinator>/ <n> --owner .admin/@<generation>` for each coordinator. It refuses a share that would bring the sum over the current cap.
  `$L cap` leaves existing shares as they are. A positive `$L cap N` refuses when the shares add up to more than N, and it writes nothing. When the user asks for a new cap, rule on shares again in the same service, in this order:
  1. Record the new ruling with `$B rule add --kind shares ... --supersedes R<n>`, naming the old shares ruling.
  2. For each share the ruling lowers, run `$L share --for <coordinator>/ <n> --owner .admin/@<generation>`. When that write is refused, clear that share with `$L share --for <coordinator>/ 0 --clear --owner .admin/@<generation>`.
  3. Run `$L cap N`. When that command is refused, finish step 2. Then run `$L cap N` again.
  4. For each share the ruling raises, and for each share step 2 cleared, run `$L share --for <coordinator>/ <n> --owner .admin/@<generation>`.
  Do not run `$L cap 0` to get past a refusal.
- `queue-order`: when no contest covers the two holders, such as an order the user states, first run `$L contest --holders <first holder>,<second holder> --owner .admin/@<generation>`. It prints `C<n>`, and a rerun prints the same id. Then `$L contest --settle C<n> --first <holder> --owner .admin/@<generation>`. What `land` then holds is in [Reporting to an executive admin](../brigade/SKILL.md#reporting-to-an-executive-admin), under A ruling's side.

Then send the `ruling` line to each coordinator involved.

**States.** A ruling starts `in-force`. Mark it `done` with `$B rule set R<n> --state done` when its condition ends. A rerun of its `lease reserve` prints `S<n> was claimed in full`, the moved ticket appears in the winner's `rail.tsv`, the share is in place, or `$L status --holder <first holder>` shows a `landed` entry. Mark it `expired` when the rerun refuses with `S<n> for ruling R<n> expired`, or its entry left the queue unordered. Rule again on the next service if the conflict remains. Recording comes first, so a crash never leaves a ruling carried out but unlogged. A rerun of `lease reserve` with the same ruling, `ticket move`, `share`, and `contest --settle` gives the same result.

**Replacing a ruling.** A new ruling that changes an earlier one names it with `--supersedes R<n>`. Remove the old constraint before carrying out the new one, with `$L lease unreserve S<n> --owner .admin/@<generation>`, a new `contest --settle`, `$L contest --cancel C<n> --owner .admin/@<generation>`, or new shares.

**Overrule.** The user can overrule any ruling by describing it. Run `$B rule overrule R<n> --decision "<the user's words>"`, which records a ruling decided by `user` that supersedes it, then carry the new one out. An overrule changes what happens next. It cannot undo a lease already claimed or work already landed. Say so. When the overrule states a general preference, ask whether to add it to `## Priorities`, and add it only when the user says yes.

**Appeals.** A coordinator appeals as [Reporting to an executive admin](../brigade/SKILL.md#reporting-to-an-executive-admin) says, under A ruling's side. When an `appeal` says compliance would be irreversible, escalate it with `$B 86 add` and act on it only after the user answers. On any other `appeal` line, recheck the ruling with the appeal's facts, such as a dependency it did not know. When the rules now decide differently, record a new ruling that supersedes the old one. Otherwise keep it, and list the appeal in the next update for the user.

**Escalate** only what the rules cannot settle. Park each with `$B 86 add --question "..." --options "..." --default "..."`. The default is the option that keeps things as they are, such as the current holder keeping the paths or the ticket staying with the admin. When no option does, such as two waiting parties, the default is the party whose name sorts first. `86 add` does not check for repeats, so first read `$B 86 list`, and when it already lists that conflict, park nothing new. When the user answers one of the admin's own questions, run `$B 86 answer Q<n> --answer "<the user's words>"` first. Act on that conflict only after that command. An answer to a coordinator's decision, including one that keeps it parked, goes back as an `answer` line. What the coordinator does with it is in [Reporting to an executive admin](../brigade/SKILL.md#reporting-to-an-executive-admin), under Requests.

- A real priority call. No rule separates the parties. One coordinator lost three rulings in a row on the same paths, or its work has waited on rulings for more than 24 hours. An ordered entry has waited more than 24 hours on an item that keeps bouncing.
- A change to a purpose. The same two purposes collided in more than three rulings in a week, or a request fits no purpose. Propose new wording. Never edit a coordinator's `menu.md`.
- Anything irreversible. Dropping or closing another coordinator's work, deleting a branch, and changing the repository cap or the landing mode belong to the user. Run `$L cap <n>` and `$L mode <mode>` only when the user asks, with no `--owner`, because neither is a ruling write, and after `$L mode`, tell every coordinator with a `from-user` line.

## What the admin never does

- Decide what belongs to the user. It sets no cap, landing mode, priority, or purpose, and never answers a coordinator's decision.
- Direct a coordinator's own work. What a coordinator builds, how it reviews, and when it submits, absent a conflict, stay its own.
- Write code, or edit any file in a repository.
- Land work. It never runs `$L submit` or `$L land`, and never merges or deletes a branch.
- Override a review. It never records or changes a verdict, never asks a coordinator to submit work that did not pass, and never messages a worker.
- Write into a coordinator's store, except new files in its `inbox/` through `ticket move` and `request`.
- Claim, renew, or release a lease, or start work. It only reserves contested paths for a ruling's winner.

## Admin recovery and retirement

The store outlives its thread. Recovery is a user request, run from one thread. [The script](../brigade/SKILL.md#the-script) says how every `brigade.py` write checks the owner token, and how `set --thread --replace` raises the landing floor. Every `land.py` ruling write checks `--owner .admin/@<generation>` against that floor. So a command the old run started either finished before the claim or is refused after it. The stop steps are a courtesy.

1. Claim the store with `$B set --thread recovering:<this thread> --replace --expect <old thread>`. Of two racing recoveries, one wins and the other exits 1. The output names the recorded schedule ids and `previousThread`. Run `$B status` again for the new owner token.
2. Delete each schedule with `delete_scheduled_task`, and clear each name with `$B set --schedule <name>=`.
3. When the old thread still exists, call `t3_thread_interrupt` on it. `status: "interrupt_requested"` means its run has not stopped yet.
4. Call `t3_thread_wait` on the run id it returned, or on the thread when it returned none.
5. When the wait returns `timedOut: true`, launch nothing. The store stays `recovering:<this thread>`. Tell the user. Recovery answers the user's request, and this thread is not the admin, so the admin's level does not apply. Wait again on the next turn on the thread in `previousThread`.
6. When the wait reports a terminal state, archive the old thread. Launch the new thread with the message from opening step 5. Run `$B set --thread <new> --replace --expect recovering:<this thread> --stopped <run id>`, `--stopped idle` for an idle thread, or `--stopped gone` when the old thread no longer exists. Without `--stopped` it exits 1 with `brigade: the old run has not been confirmed stopped; wait for it with t3_thread_wait, then pass --stopped <run id>`. Then send the start message. The new thread's first service sends every coordinator the `reports-to` line.

When the recovering thread is itself gone, a later recovery claims with `--expect recovering:<that thread>` and runs the same steps.

To retire the admin, route or drop its waiting tickets, then run `$B set --intake ""`. Delete its schedules and clear each name. Send each coordinator the `reports-to` line with `none` as `<thread>`, and send a last update. Unpin its thread. Last, run `$B set --thread "" --replace --expect <this thread>`. A later wake then finds `thread not recorded` at service step 1 and ends. A write the old thread still runs gets the stale-owner refusal in [The script](../brigade/SKILL.md#the-script). A write with `--owner @<new generation>`, the token `status` prints as `owner @<new generation>`, exits with `brigade: this store has no recorded thread; it was retired, and only set --thread --expect restarts it`. Each coordinator takes a shared source back with `set --intake <source>` where the user wants it. Restarting a retired admin is recovery with `--expect ""` and `--stopped gone`.

## What the user hears from the admin

The user hears from one thread. The admin's level uses the same three values as a coordinator's.

- `every-turn`. Reply after each wake. Each message is a wake. A coordinator's routine wake sends the admin no line, so it is not one.
- `milestones`. Reply when any coordinator's work merges, when a review sends work back or blocks it, when the user has a decision to make, when a failure arrives, when the user sends a message, and for the evening update. Every other wake ends the turn with no reply text at all. Those wakes include a `blocked` line, a `reply` line, a `contest` or `appeal` line, a ruling, a `drained` or `report` line, and a scheduled service with nothing new.
- `digest`. Reply for a decision, a failure no coordinator can fix itself, one summary when every coordinator has drained, and the evening update. Every coordinator has drained when no coordinator line in `walk` shows `in progress`, `in review`, `passed review`, or `waiting to land`.

A ruling is never a reply occasion on its own at `milestones` or `digest`. A message from the user gets at least a one-line acknowledgment at every level, and a direct question gets an answer. A coordinator's `reply` line answers something the user asked, so pass it on, including a decline and its reason. It arrives only as the message that woke the admin, so this thread carries it until that reply. At `every-turn` it goes in that wake's reply. At `milestones` and `digest` it goes in the next reply that level sends, and in the evening update at the latest.

Every admin reply follows [Digest messages](../brigade/SKILL.md#digest-messages) at every level. Say what changed for each purpose. Name each coordinator by its purpose, not its store name. List the rulings made since the last update in plain words, each with the rule that decided it, and say the user can overrule any of them by describing it. The full update that `$B close --to-file` writes holds each ruling's id and each coordinator's newest report.
