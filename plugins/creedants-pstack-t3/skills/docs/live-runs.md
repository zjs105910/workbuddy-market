# Live runs

This page records each live end-to-end run of a long pstack-t3 playbook on a real repository. It lists what merged, how long the run took, and the skill defects the run exposed. Each defect becomes its own ticket. A run changes no skill.

## Autopilot-full, 2026-10-06

### Setup

- **T3 build.** `0.0.46-nightly.20261005.2702` on Linux.
- **pstack-t3.** `main` at `c768f78`, pstack 0.15.15.
- **Repository.** `creedants/pstack-t3-sandbox`, a private scratch repository with one Python module, `stats.py`. CI runs `python -m unittest discover -s tests -v` on Python 3.12. It allows squash merges only and deletes branches on merge.
- **Queue.** Four issues, one PR each:
  1. `median` returns the upper middle value for even-length input.
  2. `mode` should raise a clear error on empty input.
  3. Add `variance` and `stdev`.
  4. Add a `python -m stats` command line. It depends on #3.
- **Launch.** One root thread on Claude Opus 5.5 in the project root, started with `$poteto-mode full autopilot`. The message named the four issues and gave full autonomy to merge on a clean verdict. The operator answered no question during the run, because the playbook asked none.
- **Seats since this run.** The owners ran on Grok 4.7 Build Fast, and one owner picked Claude Haiku 4.5 by hand (defect 3). `roles.py` no longer returns either one. A fast Grok id and Claude Haiku 4.5 are excluded seats, and no mode or budget turns them on (#96, #98).

### What happened

The root resolved roles with `roles.py show`, chose `gh` as the forge, and wrote an owner brief and a verifier brief to its state directory. Within three minutes it launched three owners with `t3_thread_launch`. Each owner ran Grok 4.7 Build Fast in its own worktree off `main`. The root held #4 until #3 merged and armed the hourly audit tick with `schedule_task`.

Each owner opened a ready PR with a red test within five minutes of launch, linked it with `link_pull_request`, and waited on CI with `watch_pull_request`. For every round, the root ran four `delegate_task` verifiers at the reported head. Each verifier ran on a model family other than Grok:

| Lane | Model |
| --- | --- |
| Gates | GPT-6.1-Sol |
| Live and regression against `main` | Claude Opus 5.5 |
| Spec parity with `statistics` | Gemini 3.8 Flash |
| Robustness | Composer 2.5 |

| Issue | PR | Rounds | Merged (UTC) | Minutes from launch |
| --- | --- | --- | --- | --- |
| #1 | #6 | 1 | 10:56 | 13 |
| #2 | #5 | 1 | 10:59 | 16 |
| #3 | #7 | 3 | 11:13 | 30 |
| #4 | #8 | 4 so far | Open | Over 99 |

The verifiers caught real defects before merge:

- **#3, round 1.** `variance` and `stdev` called `len()` first, so a generator raised `TypeError`. Three lanes on three models found it independently.
- **#3, round 2.** The fix caught every `StatisticsError` and relabelled errors that the caller's own generator raised. Only the live lane found it. The spec lane passed that head.
- **#4, rounds 1 to 4.** Very large numbers and undecodable stdin ended in a Python traceback. `mean` printed `inf` with exit 0 on input that `statistics.mean` handles. Later rounds found wrong error labels, an integer padded with leading zeros that lost precision, and whole numbers in non-ASCII digits that lost precision. After round 2 the root asked for a redesign of the token parser instead of another patch.

The merge of #2 put #3's open branch in conflict with `main`. The root cancelled that round's verifiers with `task_cancel` and had the owner rebase. It started a fresh round on the new head. Every merge came from a head rebased onto `main`, with CI green on that head and a patch-id equal to the verdict's. The hourly tick fired once at 11:45 and found nothing stuck.

### State at the end of the record

This record stops at 12:22 UTC, 99 minutes after launch, at the end of the observer's timebox. The run was still progressing, so the observer did not stop it.

- `main` is at `3bdc46c` with #1, #2, and #3. CI passed on it.
- Issues #1, #2, and #3 are closed by their PRs. Issue #4 is open.
- PR #8 is open at its round 4 head. At 12:21 the root sent the owner round 4's verdict, not clean, with a precision finding on whole numbers in non-ASCII digits. The owner was fixing it for round 5.
- The only remote branches are `main` and the #4 branch.

The run had launched 61 threads by then. That count is the root, 4 owners, 40 verifier children in 10 rounds, and 16 children the owners started. The root cancelled one round of verifiers when its head went stale. The owner children were 5 Comment Sicko reviews, 3 trail reviews, 1 explanation, 5 design runners, 1 design judge, and 1 implementation child.

### How the run finished

This part is after the 12:22 UTC cutoff. The run continued. The observer left it alone.

PR #8 merged at 12:32:53 UTC, 109 minutes after the 10:43 UTC launch. The squash commit on `main` is `486a5b7`, subject `feat(stats): add python -m stats (#8)`. The `test` check on that commit succeeded at 12:33:05 UTC.

#4 took 5 review rounds. The first four are the rounds in the cutoff record. Round 5 started at 12:23 UTC on head `5306f0a`, after the owner fixed whole numbers written in non-ASCII digits. Gates, live and regression, spec, and robustness all passed. The root sent a clean verdict for `5306f0a` at 12:32:02 UTC. The rebase onto `main` changed nothing. The owner squash-merged at 12:32:53 UTC.

The root deleted its hourly audit tick at 12:35:32 UTC, after the four PRs merged. The sandbox project has no scheduled task.

The root removed its two verification worktrees, `verify/4-cli-5306f0a` and `verify/trunk-3bdc46c`, at 12:33:50 UTC. The `verify/` directory remains, and it is empty. The root left the four owner worktrees in place. Its closing note says T3 still links them to the owner threads, and none has unsaved work. A listing on 2026-10-06 shows `pstack-median-even`, `pstack-mode-empty`, `pstack-variance-stdev`, and `pstack-cli` under `~/.t3/worktrees/pstack-t3-sandbox/`, each with a clean status. GitHub lists one remote branch, `main`. The #4 owner recorded that the remote branch was deleted with the squash merge.

- `main` is at `486a5b7`. The `test` check passed.
- Issues #1, #2, #3, and #4 are closed. Issue #4 closed at 12:32:54 UTC.

### Defects found

1. **Autopilot-full names no channel between owners and the root.** Steps 2, 4, and 5 of `t3/overrides/poteto-mode/playbooks/autopilot-full.md` have owners report the code-ready head, merge-ready, and the merge, and have the root send verdicts. They do not say how. An owner is a top-level thread with no parent, so its finished turn never wakes the root. The runtime's Top-level threads section (`t3/runtime.md`, lines 175 to 193) does not say so either. The root invented a protocol of one-line `CODE-READY`, `MERGE-READY`, `MERGE-PREP`, and `MERGED` messages, sent with `t3_thread_send` and `mode: "queue"`. It sent verdicts the same way with `mode: "auto"`. That protocol worked, but another root may not invent it. **Fix.** Write that protocol into step 2 with the root's thread ID in each owner brief. State in the runtime that a launched thread's turns do not wake the launcher.

   **Protocol since this run.** Owners now send their report lines with `mode: "auto"`, not `"queue"`, and the root's verdicts stay on `"auto"` (#92). `auto` starts an idle root, steers a running turn, and queues behind a turn that cannot accept steering yet. The root checks the head each line names, because arrival order never makes a head current. Brigade's event lines to an executive admin stay on `"queue"`. The record above keeps the `"queue"` protocol the root invented.
2. **The build drops the exec bit on `watch-pr`.** `scripts/build.py` copies files with `shutil.copyfile` and then marks only `.sh`, `.py`, `.mjs`, and `orch.ts` files executable (lines 120 to 122). `vendor/pstack/skills/poteto-mode/scripts/watch-pr/watch-pr` is mode `100755`, and the built copy is `100644`. Step 6 of `t3/overrides/poteto-mode/playbooks/babysit.md` says to run it directly. Running `skills/poteto-mode/scripts/watch-pr/watch-pr --status-only` fails with `Permission denied`. During the run, one owner ran it through `bun` instead. That call hit a JSON parse retry loop that did not reproduce later, and the owner fell back to `gh api`. **Fix.** Copy the source mode with `shutil.copymode`, and add a test that every built file keeps its vendor mode.
3. **`no-comments` names no pstack role for Comment Sicko.** Step 1 of `t3/overrides/no-comments/SKILL.md` (line 19) gives the T3 task role `review` and no role to resolve the target from. Three owners chose three different seats for the same step: `judgment and prose` on Claude Opus 5.5, Claude Haiku 4.5 picked by hand without `roles.py`, and Grok 4.7 Build Fast. One owner wrote that "the skill specifies review without a pstack name". **Fix.** Name the pstack role that seats Comment Sicko in step 1, such as `judgment and prose`, and list it in the runtime's Role names table.
4. **`roles.py show` keeps only the last `--role`.** `t3/scripts/roles.py` declares `--role` without `action="append"` (line 600). `roles.py show --role "bug-fix" --role "judgment and prose"` prints only `judgment and prose` and gives no error. One owner asked for two roles and had to rerun the command. **Fix.** Accept repeated `--role` flags, or reject a repeat with an error.

### Observations that are not pstack-t3 defects

- **Fix rounds have no bound.** On #4 each round's live lane found a new, narrower edge case in number parsing, and the playbook sends every proven finding back to the owner. Nothing in step 4 weighs a finding against the issue's scope, so a small command line had taken four rounds by the end of the record. The rule is upstream's.
- **The design pass costs more than the change.** poteto-mode sends any code that crosses a function boundary to the architect skill. The #4 owner ran five architect runners for a 69-line command line. The slowest runner ran for about 12 minutes, from 11:19:52 to 11:31:52 UTC. The design pass, from that runner's start to the owner's launch of its implementation child at 11:36:41 UTC, took about 17 minutes. Three owners noted the tension with the 15-minute deadline for a first PR. The rule is upstream's, so a change belongs upstream.
- **A watch wake does not name the head.** The stored wake text is `#5: checks passed`. One wake arrived after a rebase, and the owner read it as news about the old head. The runtime's rule that a wake is news held, because the owner re-read the PR before merging.
- **The root settled between turns.** T3 settled the idle root after it launched the last owner. The next `t3_thread_send` and the hourly tick both still woke it. The root held no watch, so settling cost nothing.
