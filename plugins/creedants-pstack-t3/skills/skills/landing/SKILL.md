---
name: landing
description: "Let many agents write to one repository at once without collisions: a per-repository landing contract, path leases claimed before work starts, one queue that is the only writer to trunk, and a machine-wide slot governor for builds and tests. Use for 'landing', 'land this', 'merge queue', 'many agents on one repo', 'where does this work land', or before any coordinator (brigade, Orchestrate, Autopilot, swarm) delegates writing work in parallel."
---

# Landing

Read [the pstack-t3 runtime](../pstack-runtime/SKILL.md) before spawning workers, choosing models, scheduling, or isolating work. It maps those steps onto T3's orchestrator tools.

Writing scales. Integration does not. Landing makes integration a property of the repository, decided once, so no coordinator asks where work lands and no two writers collide.

The rules:

1. One trunk per repository. Every change lands there through the queue.
2. A writer claims a lease on the paths it will change before it starts. Overlapping claims are refused.
3. Writers never integrate. A worker commits in its own worktree and stops. It never merges, rebases a shared branch, or pushes trunk.
4. The queue is the only writer to trunk. It is a lock, not a process. Whoever runs `land` while the lock is free drains the queue. Everyone else gets "queue busy" and moves on.
5. A review verdict holds only for the exact change reviewed. The queue lands the pinned SHA, and bounces it when the rebased change differs from the reviewed one.
6. Builds and tests run under a governor slot, so the machine is not overrun.

## The script

`<skills>/landing/scripts/land.py`, where `<skills>` is the directory holding this skill. Run it from any checkout of the repository, or pass `--repo <path>`. State lives in SQLite under `${XDG_STATE_HOME:-~/.local/state}/pstack-t3/landing/`, one store per repository.

```bash
L="python3 <skills>/landing/scripts/land.py --repo <checkout>"
$L init --trunk main --mode human|merge|push|local --check "<cmd>" [--check ...] [--setup "npm ci"] [--batch 4] [--timeout 1800] [--merge-method merge|squash|rebase] [--base <commit>] [--cap 4]
$L mode merge [--merge-method squash]   # change the mode while the queue is empty. --merge-method may change while entries await merge
$L cap 4                     # most changes in flight on the repository at once; 0 clears it
$L lease claim --holder <restaurant>/<dish> --paths src/engine,package.json [--owner <restaurant>/@<generation>]   # prints L<n>, who holds the overlap, or the cap and its holders
$L lease check --holder <restaurant>/<dish> --paths src/engine   # what a claim would answer now, with no lease claimed and no reservation armed: free, the overlapping leases, or the cap
$L lease renew L3 [--if-live] [--owner ...] ; $L lease release L3 [--owner ...] ; $L lease list
$L submit --holder <restaurant>/<dish> --branch <b> --sha <reviewed sha> --lease L3 --reviewer <provider/model> [--owner ...] [--title "..." --body-file pr.md]   # prints E<n>
$L owner --prefix <restaurant>/ --generation 2   # raise a holder prefix's floor; it never lowers
$L lease reserve --for <restaurant>/ --paths a.md,docs --ruling R<n> [--ttl-hours 2] --owner .admin/@<generation>   # prints S<n>; refuses other holders' claims on those paths
$L lease unreserve S<n> --owner .admin/@<generation>   # lift a reservation
$L share --for <restaurant>/ <n> [--clear] --owner .admin/@<generation>   # that prefix's share of the cap; --clear takes 0
$L contest --holders <a>,<b> --owner <restaurant>/@<generation>   # prints C<n>; land holds both holders' entries
$L contest --settle C<n> --first <holder> --owner .admin/@<generation>   # the first holder lands, then the other
$L contest --cancel C<n> --owner .admin/@<generation>   # remove the hold or the order
$L land                      # drain the queue; prints what landed, bounced, or is still queued
$L status [E3] ; $L resume
$L status --holder <restaurant>/<dish>   # that holder's entries with their SHAs; a value ending in / matches every holder under it
$L status --holder <restaurant>/<dish> --sha <sha>   # only its entries at exactly that commit
$L slot -- npm test          # run a heavy command under a governor slot
$L slot --exclusive -- npm run bench   # hold every slot: nothing else heavy runs while it measures
```

Every command takes `--help`.

A coordinator replaced by another thread must not write again. `owner --prefix docs/ --generation 2` raises the floor for holders under `docs/` and never lowers it, so a rerun changes nothing and a lower generation exits 1. `lease claim`, `lease renew`, `lease release`, and `submit` take `--owner <prefix>@<generation>`, whose prefix the holder must start with. Inside the write's transaction each refuses a generation below the prefix's floor with `land: owner docs/@1 is stale; docs/ is at generation 2`, and refuses a holder under a floored prefix that passes no `--owner`. A prefix with no floor works without `--owner`. brigade's `set --thread --replace` raises its restaurant's floor before it records the new thread.

## Rulings

The executive admin carries out its rulings with `lease reserve`, `lease unreserve`, `share`, and `contest`. Every ruling write takes `--owner <prefix>@<generation>`, usually `.admin/@<generation>`, and checks it against that prefix's floor first inside its own transaction. A stale one exits 1 with `land: owner .admin/@1 is stale; .admin/ is at generation 2` and changes nothing.

`lease reserve` saves paths for a holder prefix. Every admission refuses another holder's overlap with a standing reservation, with `paths reserved for docs/ by ruling R4 until <time>`. That covers `lease claim` and the re-admission of an expired lease in `lease renew`. A reservation waits until no other holder's live lease overlaps it and the cap and the prefix's share have room. Then it arms, oldest first, in the same transaction as a claim, a `lease release`, or a landing that releases the lease. An armed reservation counts as one change in flight while the winner holds no live lease taken from it. While one is live, the lease and the reservation count once. When every lease taken from it is released or expired, the reservation counts again, so the winner still has room to claim the rest. A winner's claim removes the reserved paths it covers, and the rest stay reserved. The reservation expires 2 hours after it arms, or `--ttl-hours` after. A reservation names the contested paths. It refuses an empty path or `.`, which would hold the whole repository. A rerun with the same ruling prints the same `S<n>`, or `S<n> was claimed in full` once the winner has claimed every path. `lease list` and `lease check` show reservations. `lease check` claims no lease, arms no reservation, starts no hold, and adds no log row. Like every command that opens the store, it upgrades an older store's schema. For a waiting reservation that a claim would arm, it prints the `until <time>` a claim made at that moment would set.

`share` sets a holder prefix's share of the cap. Admission refuses a claim that would put the prefix over it, with `docs/ is at its share: 2 of 2`. Shares that add up to more than the cap are refused.

`contest --holders` holds every entry of both holders out of `land`, queued now or submitted later. It refuses when either holder already has an entry landing, awaiting merge, or landed. `--settle` turns the hold into an order. `land` holds the other holder's entries until an entry of the first holder lands, so a bounce and a resubmit keep the order. Settling again replaces the order until the first holder has an entry landing or awaiting merge. After that the order stands, because an open PR can merge on its own. An order that would close a cycle with another settled contest is refused. `land` prints a held entry as `E2 (held by C1)`. Every form of `contest` waits for the queue lock, so it never changes a running `land`.

## Set up a repository once

Run `init` the first time any coordinator writes to a repository. The mode decides whether the user stays a gate on landing, so it is the user's choice. brigade asks it when a restaurant opens. Any other coordinator asks once per repository with the host's question tool, unless the user already said.

In `merge` mode, `init` runs `gh repo view --json mergeCommitAllowed,squashMergeAllowed,rebaseMergeAllowed`. With no `--merge-method`, it stores the only allowed method. When several methods are allowed and merge is allowed, it stores merge. When merge is not allowed, it stores squash. An explicit method the repository disallows is refused, and the error names the allowed methods. When `gh` fails, `init` stores merge, or the `--merge-method` you passed. The method is checked against the repository whenever it is set, in any mode, and whenever the mode becomes merge. `mode merge` swaps a stored method the repository disallows for an allowed one and names it.

The cap belongs to the repository like the mode does. It bounds changes in flight. Those are every submitted lease and every active lease that has not expired, whichever coordinator holds it. The coordinator that opens first sets it with the mode, as `init --trunk main --mode merge --cap 4`, and `land.py cap N` changes it later. A claim at the cap is refused with `repository at its cap: 4 of 4 changes in flight (<holders>)`. `status` shows `changes in flight: 3 of 4` while a cap is set. The executive admin divides the cap into shares with `land.py share`, and `land.py cap N` refuses a positive cap below the current sum of those shares.

| Mode | Landing does | The user |
| --- | --- | --- |
| `merge` | Opens a PR and merges it, per [Pull request lifecycle](#pull-request-lifecycle). | Reviews after the fact. Nothing waits on them. |
| `human` | Opens a PR and leaves it open for the user to merge, per [Pull request lifecycle](#pull-request-lifecycle). | Merges every PR. |
| `push` | Rebases, runs the checks, and pushes trunk only if the remote is still at the tested base. No PRs. | Reviews after the fact, in the commit history. |
| `local` | Lands on `refs/landing/<trunk>`, which no checkout uses. Pass `--base`. | Merges the lane into a branch when ready. |

`merge` and `push` let reviewed changes reach trunk with no human gate. When the PR needs an approving review, or when it has changes requested, the queue pauses and names the PR and that requirement. It does not run `gh pr merge --auto`. The user then either relaxes the rule for the queue or switches to `human`.

Checks are the repository's own test, type check, and lint gates. `--setup` installs dependencies, because the queue's worktree is cleaned with `git clean -ffdx` before every attempt. `land.py mode` switches between `merge`, `human`, and `push` once nothing is queued, landing, or awaiting merge. `land.py mode --merge-method` changes the method the next `gh pr merge` uses, and it may run while entries are queued, landing, or awaiting merge. Changing trunk or remote, or moving to or from `local`, needs a new contract.

## Run writers through it

[The runtime's Modes section](../pstack-runtime/SKILL.md#modes) sets the mode lines of every brief this skill writes and how its spawns run in light mode.

For every unit of writing work:

1. **Claim.** `lease claim` the files and directories the unit will change, before delegating. When the claim is refused, fold the unit into the holder's work or hold it until that lease is released. A cap refusal names every holder in flight. Hold the unit until one of them releases. Never claim `.` unless the unit really touches everything. `lease renew` extends a live lease. Renewing an expired lease is a new claim on its paths. It is refused when another holder's lease now overlaps or the cap is full, and the refusal names which. `--if-live` refuses an expired lease instead, so admitting it again is always a separate step taken after the old worker stopped.
2. **Brief.** A writer is a worktree thread from `t3_thread_launch` when it runs long or the user should see it, and a `delegate_task` child otherwise. Tell the worker to work only in its own worktree branched from `<remote>/<trunk>` (or `refs/landing/<trunk>` in local mode), change only the leased paths, keep history linear with no merge commits, run builds and tests through `land.py slot --` and every benchmark or timing measurement through `land.py slot --exclusive --`, commit, and report the branch and head SHA. Put rule 3 in the brief unchanged.
3. **Review** the exact SHA with a verifier from another model family, per the coordinator's own review step.
4. **Submit** that SHA with the lease and the reviewer. In `merge` and `human` mode, pass `--title` and `--body-file` so the PR says what changed and how it was verified. The queue sends the submitted title and body unchanged and adds no line to them. With no `--body-file`, the body is the reviewed commit's body. The reviewer stays in the queue's local store. A submit that changes paths outside the lease is refused. Widen the lease or split the change.
5. **Land.** Run `land`. When it prints "queue busy", another run will take the entry.
6. **Settle.** Read `status E<n>`.
   - `landed`: the lease is released. Record it in the coordinator's tables, then remove the worker's worktree with `git worktree remove` and delete its branch.
   - `bounced`: the lease is active again for the fix. Submitting that change again prints a new entry id. The bounced id is not reused. Call `unwatch_pull_request` on the PR the bounce left open. Fire a fresh worker with the original brief, the bounce reason, and current trunk. A conflict or a changed rebase needs a new review after the fix.
   - `awaiting-merge` (`merge` and `human` mode): the PR is open. [Pull request lifecycle](#pull-request-lifecycle) says what the next `land` does with it.

## Keep the queue moving

While any entry you submitted is `queued` or `awaiting-merge`, keep the queue moving. Drains from other coordinators on the same repository are harmless, because the queue lock runs one at a time. `land` prints every holder's entries. Act only on lines whose holder is this coordinator's own, and call `watch_pull_request` only on those PRs. A sibling's PR is the sibling's to watch. When a sibling's `land` opens your PR, read its URL from your own `status --holder <restaurant>/<dish>`, which brigade's `watch` prints as `awaiting merge <pr url>`.

In `merge` and `human` mode, once `land` has opened a PR, this thread calls `watch_pull_request` on that PR per [Pull request watching](../pstack-runtime/SKILL.md#pull-request-watching). This thread owns the PR. A worker child cannot watch. On each wake, run `land` and act on what it prints. When that wake's `land` prints `queue busy`, run `land` again before ending the turn, at most 3 more times, waiting 5 seconds before each try. The passed-checks wake is spent, so this thread would otherwise notice the merge only from the hourly heartbeat. Keep the watch while the entry is queued or awaiting merge. An interim status reply keeps the watch. Call `unwatch_pull_request` only when this thread stops driving that PR or hands the queue back to the user. Driving stops when that PR closes, when the queue bounces it and leaves it open, or when this thread stops owning the queue.

Keep one `schedule_task` heartbeat for a `queued` entry that has no open PR yet, and beside every watch. Create that heartbeat only if none is running, and reuse it across frontiers. The heartbeat exists because a PR with no posted check never wakes the watch, and because a merge never wakes the watch. In `merge` mode on a repository with required checks, when the PR is not in a merge queue, use `{"type": "interval", "everyMs": 3600000}`. While an entry is `awaiting-merge` in `human` mode, or `gh api graphql` reports that `PullRequest.isInMergeQueue` is true for that PR, the heartbeat is required and uses `{"type": "interval", "everyMs": 900000}`. That interval is the exception in [Pull request watching](../pstack-runtime/SKILL.md#pull-request-watching). The prompt is "Run `python3 <skills>/landing/scripts/land.py --repo <checkout> land` and act on what it prints per the landing skill." If the running heartbeat has the other interval, delete it with `delete_scheduled_task` and create it again. Do not drop the heartbeat in `merge` mode. Delete it with `delete_scheduled_task` when `status` shows nothing queued or awaiting merge. A crashed run is recovered by the next one. It asks git whether the last attempt was published before it retries.

## Pull request lifecycle

This section states once what `land` does with an entry's pull request in `merge` and `human` mode. The mode table and step 6 of [Run writers through it](#run-writers-through-it) link here.

### Open

In both modes `land` rebases onto trunk, runs the checks, pushes `landing/e<n>`, and opens a PR. An open pull request on `landing/e<n>` is adopted, and so is a closed or merged one whose head is this entry's candidate. A closed or merged pull request at another head is a reused id. `land` then opens a new pull request on `landing/e<n>`, and first pushes the checked candidate there when git lists no such branch on the remote.

### Merge

In `merge` mode `land` reads posted checks before it runs `gh pr merge`, including `--auto`. It merges when a check read succeeds and no posted check is pending or failed. A pending posted check waits. A failed posted check bounces an open PR, including one already noted `merge requested by the queue`, and makes the lease active. The first land that sees no posted check records that run and waits. A later `land` merges when checks are still absent. To merge, `land` runs `gh pr merge --auto` first. When that command succeeds, `land` runs no plain merge. When it fails, `land` runs the plain `gh pr merge`. Either success notes the entry `merge requested by the queue`. When that plain merge fails, the entry waits and the queue does not pause only when no check is posted and the refusal says the base branch policy prohibits the merge. Every other plain merge failure pauses the queue and names that failure, including when the `--auto` attempt said auto-merge is disabled. A failed or unreadable check read pauses the queue and does not merge.

In `human` mode `land` leaves the PR open and marks the entry landed when someone merges it.

### Bounce

This subsection covers `merge` mode. The check read includes `autoMergeRequest`. The bounce runs `gh pr merge --disable-auto` only when that field is not null, and leaves the PR open. It posts no comment. Any other bounce of an open PR in this mode does the same. When the field is null, the bounce does not call `--disable-auto`. When that call fails, the PR can still merge on its own, so the queue pauses instead of bouncing, per [When the queue pauses](#when-the-queue-pauses).

### Merged

Every `land` after the one that opened or adopted the PR reads the PR state before it reads checks. A PR already merged at the candidate head is landed in that run per [Branch cleanup](#branch-cleanup), even when one of its checks failed. For an entry noted `merge requested by the queue`, `land` reads the PR state again after the check read and before it acts on a failed check, so a PR that merged between the two reads is landed and not bounced. For any other entry, a failed check bounces with no second state read.

### Branch cleanup

In both modes `land` deletes remote `landing/e<n>` after the PR merges. When the server accepts the delete, the entry lands. When the delete fails, `land` asks the forge when the contract remote has exactly one push URL and that URL names the same owner/repo `gh repo view --json nameWithOwner` resolves. It asks `gh api repos/{owner}/{repo}/branches/landing/e<n>`, and that answer alone decides whether `landing/e<n>` exists. HTTP 404 lands the entry. HTTP 200, or any other result, leaves the entry for the next run. Where the forge cannot be asked, a failed delete lands the entry only when git says `landing/e<n>` does not exist and `gh pr view` shows the PR was opened from another branch. An older queue opened such a PR on `landing/q<n>`, and the queue leaves that branch in place. Any other result there leaves the entry for the next run. `land` also deletes a local `landing/e<n>` branch when one exists and git can delete it. When that delete fails, `land` still marks the entry landed and prints the branch it left.

## When the queue pauses

`land` pauses the queue when trunk no longer contains the last landed commit, because someone rewound or replaced it. That is the user's call. Report it as a decision with the two commits from the message. Run `resume` only after the user confirms trunk is right.

When `land` cannot turn off auto-merge on a PR whose checks failed, the pause names the PR and the failure, and the entry stays awaiting merge. Turn auto-merge off on GitHub, then run `resume`, then `land`, which bounces the entry.

When GitHub refuses the merge method, the pause names `land.py mode merge --merge-method` with an allowed method, then `land.py resume`. Run that mode command, then `resume`, then `land`.

## Capacity

The governor defaults to one slot per four cores, at most four. Set it in `${XDG_STATE_HOME:-~/.local/state}/pstack-t3/governor/governor.json` as `{"slots": N}`. Landing checks use their own slot, so workers never starve the queue. A command already inside a slot runs nested commands without taking another. Dev servers do not take slots. Start them with the preview tools.

A measurement taken while other work loads the machine is wrong, not noisy. `slot --exclusive` takes the landing slot and every worker slot in a fixed order, waits for running heavy commands to finish, and holds them until the measurement ends. It must be the outermost slot. Nested inside another slot it refuses.
