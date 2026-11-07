# landing plan

landing lets 10 to 100 agents write to one repository at once. Writing scales freely. Integration does not. landing makes integration a property of the repository, decided once, and shared by every brigade restaurant and pstack playbook that writes to it.

## Rules

1. One trunk per repository: the branch everything lands on. Nobody asks where work lands after `init`.
2. Leases prevent conflicts at planning time. A writer claims the paths it will change before it starts. Overlapping claims are refused.
3. Writers never integrate. A worker commits in its own worktree. It never merges, rebases shared branches, or pushes trunk.
4. One landing queue per repository is the only writer to trunk. The queue is a lock, not a process. Whoever runs `land.py land` while holding it drains the queue.
5. Heavy commands take a slot from a machine-wide governor. Landing checks have their own slot.
6. A review verdict holds only for the exact change reviewed. The queue lands the pinned SHA and bounces it when the rebased change differs.

## Implementation

`t3/added/landing/scripts/land.py`, Python standard library only. Tests: `tests/test_landing.py`.

- **Identity.** A store belongs to one git common directory, so every worktree of a clone shares it and another clone cannot. `init` refuses to change trunk, mode, or remote on an existing contract.
- **State.** SQLite in WAL mode under `${XDG_STATE_HOME:-~/.local/state}/pstack-t3/landing/<repo>-<hash>/land.db`. Every change is one short `BEGIN IMMEDIATE` transaction. No git command or check runs inside a transaction.
- **Locks.** `.queue.lock` is held with `flock` for a whole landing run. Lock files are never deleted. Python opens descriptors close-on-exec, so a child process cannot keep the lock.
- **Leases.** Paths are normalized with `posixpath.normpath`, and paths leaving the repository are refused. A lease is mandatory to submit, must belong to the submitter, and must cover every changed path. Renames count as a delete plus an add. A submitted lease does not expire. It is released when its entry lands and reactivated when it bounces.
- **Pinning.** `submit` records the merge base and pins the SHA at `refs/landing/pins/<sha>` before the entry row exists, so a queued entry always has its pin. The queue replays only `base..pin`, so later commits on the branch never land. Merge commits are refused.
- **Fingerprint.** A SHA-256 of `git diff --binary --full-index --no-renames --no-textconv -U0`, with `index` lines and hunk line numbers removed. Whitespace, modes, and binary content count. Line offsets from unrelated trunk changes do not.
- **Integration worktree.** Detached, owned by the queue, `reset --hard` and `clean -ffdx` before every attempt. After the checks, the queue refuses to publish if the checks changed tracked files.
- **Checks.** Each check runs in its own process group under a timeout. On timeout the whole group is killed, and the queue stops waiting for any descendant that escaped the group. Output is read as bytes.
- **Infrastructure failures.** A push the remote rejects while trunk has not moved, or a cherry-pick that fails for a reason other than a conflict, is not the entry's fault. The queue requeues the entry, pauses, and reports git's reason.
- **Crash recovery.** Before publishing, the queue writes an attempt row with the base, the candidate, and the entries. The next run asks git whether the candidate reached trunk, then marks the entries landed or requeues them.
- **Publishing.** The modes are `merge`, `human`, `push`, and `local`. `auto` is the old name of `push` and is still accepted. `push` pushes with `--force-with-lease=refs/heads/<trunk>:<tested base>`, so the push succeeds only when the remote is still at the tested base. `local` moves `refs/landing/<trunk>` with a compare-and-swap `update-ref`. No branch is ever moved under a checkout. `merge` and `human` push `landing/e<n>`, record the pushed candidate, then adopt or open the PR with `gh`, so a crash between the two is safe to rerun. `land` adopts a PR already open on `landing/e<n>`, and a closed or merged one only when its head is the entry's checked candidate. Otherwise it opens a PR there, and first pushes the checked candidate to `landing/e<n>` when git lists no such branch on the remote. A later run marks the entry landed when the PR merges at the checked head, and bounced when it closes or merges with a head the queue did not check. In `merge`, the queue reads posted checks before any `gh pr merge`, including `--auto`. A pending posted check waits. A failed posted check bounces. A failed or unreadable check read pauses the queue and does not merge. It merges only when that read succeeds and no posted check is pending or failed. After the PR merges, it deletes remote `landing/e<n>`, and the entry lands when the server accepts the delete. When the delete fails and the forge can be asked, HTTP 404 lands the entry and any other answer leaves it for the next run. Where the forge cannot be asked, the entry lands only when git says `landing/e<n>` does not exist and `gh pr view` shows the PR was opened from another branch. It deletes a local `landing/e<n>` when git can. When that local delete fails, the entry still counts as landed and `land` prints the branch it left.
- **Rewinds.** The queue records the last landed commit in every mode. When trunk no longer contains it, the queue pauses until `land.py resume`.
- **Encoding.** Git output is decoded with `surrogateescape` and paths are read NUL-separated, so non-UTF-8 content and non-ASCII file names fingerprint and match leases correctly.
- **Batching.** `--batch N` applies to `push` and `local` only. It checks up to N entries together. When a batch fails its checks, the next round tries one entry alone, then the round after that batches again. `merge` and `human` land one entry at a time.
- **Governor.** One slot per four cores, at least 1 and at most 4, overridden by `governor.json`. Nested `slot` calls inside a slot do not take another.

## Design review

Codex (gpt-6.1-sol) reviewed the design before the build and raised 14 blockers. Each is addressed above. Grok (grok-4.7) then reviewed the implementation and reproduced 10 defects, each fixed with a regression test in `tests/test_landing.py`: a queued entry briefly without its pin, a check escaping its process group, a human-mode crash after PR creation, policy rejections retried as trunk moves, non-UTF-8 check output and file contents, no rewind check in human mode, PRs merged with an unchecked head, quoted non-ASCII paths, and a missing git identity. The design decisions:

| Finding | Decision |
| --- | --- |
| Two clones sharing one store | Key the store by git common directory. |
| Long checks block every mutation | Split the queue lock from short SQLite transactions. |
| A crash strands queued work | Coordinators keep a drain schedule. Every run recovers the previous one. |
| TSV state is not transactional | SQLite with an attempt manifest. |
| An inherited lock outlives the runner | Close-on-exec descriptors, permanent lock files, process-group kill on timeout. |
| The branch moves after review | Pin the SHA under a queue-owned ref. |
| Merge commits lose their resolution | Refuse merge commits. |
| `git patch-id` ignores whitespace | Own fingerprint with whitespace, modes, and full binaries. |
| Expired or aliased leases | Mandatory, normalized, owner-checked leases that hold through landing. |
| A dirty integration worktree | `clean -ffdx` before, tracked-file check after. |
| Batch fallback built on a failed tip | Rebuild every single attempt from current trunk. |
| A human rewinds trunk | Push with an exact-base lease and pause on rewinds. |
| Local mode moves a checked-out branch | Land on `refs/landing/<trunk>`, which no checkout uses. |
| Human mode stalls the queue | PRs are independent and based on trunk. Waiting happens across runs, not under the lock. |

## Not in v1

- Cloud workers. Codex Cloud, Claude cloud sessions, and cua sandboxes can be stations that push a branch, because landing only needs a branch, a lease, and a reviewed SHA. Each adapter needs a live probe before the skill relies on it.
- Batch bisection. Today a failed batch tries one entry alone, then batches the rest again.
