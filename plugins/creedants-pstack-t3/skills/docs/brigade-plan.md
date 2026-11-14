# brigade plan

brigade gives each project, or each focus area inside a project, its own standing coordinator thread. It replicates the setup Lauren Tan describes in her livestream with Matt Pocock ([video](https://www.youtube.com/watch?v=MN9dGgmLyso), around 39:00 to 53:00). She runs more than ten coordinators, one per area. Each delegates and supervises and never does the work itself. She moves between them and reviews what landed.

brigade has no overall coordinator. The user moves between restaurants. An optional executive admin serves the user on one repository, and rules on conflicts between its coordinators by published rules that the user can overrule.

## Roles

| Term | Meaning | Built on |
| --- | --- | --- |
| Executive chef | The user. | |
| Restaurant | One project, or one focus area inside a project. A project may hold several. | T3 project |
| Head chef | One long-lived top-level thread per restaurant, pinned in that project. It never writes code. | `t3_thread_launch` with `projectId`, `t3_thread_organize` pin |
| Executive admin | One optional thread per repository that works for the user across its coordinators. It routes requests and shared intake, writes one update, and rules on conflicts between coordinators by published rules the user can overrule. It never writes code or lands work. | `brigade.py open --admin`, `rule`, `request`, `sync`, and `land.py` reservations, shares, and contests |
| Menu | The restaurant's purpose, what good looks like, non-goals, and budget. | `menu.md` |
| House rules | Standing orders pasted into every brief. They name forbidden paths, the verification bar, and that work lands through the repository's landing queue. | `house-rules.md` |
| Rail | Append-only intake. The head chef groups related tickets before it fires any. | `rail.tsv` |
| Suppliers | Scheduled intake from GitHub issues, labels, and notifications. | `schedule_task` |
| Station | A worker that runs one pstack playbook in its own worktree thread, briefed by `brigade.py brief`. | `t3_thread_launch` with a worktree strategy, `$poteto-mode` |
| Commis | Read-only prep: research, repro, scouting. | Read-only children, `how`, `why` |
| Banquet | A one-off program with an end. | Orchestrate playbook |
| Pass | Every result is checked against its ticket and the menu by a verifier subagent on a different model family than the author. | `delegate_task` from the `verifiers` role, `pass.tsv` keyed by head SHA |
| 86 board | Items that need the user: blocked work, irreversible actions, product calls. The only interrupt. | `86.md` |
| Line check, close-out | Morning brief and end-of-service report: what landed, how it served the menu, what to sample. | `schedule_task` `fixed_time` bound to the head chef thread |
| Recipe book | A mistake several stations repeat becomes a lint, type, or skill. | `correct` |
| Inspection | Weekly review of the restaurant's threads. | `reflect` |

## Voice

The kitchen terms name files, commands, and process steps only. They never reach speech. A head chef, station, or verifier writes in pstack's voice from `poteto-mode`: plain, short, direct engineering prose. Reports say "merged", "blocked", "needs your decision", never "plated", "86'd", or "heard, chef". The SKILL.md states this rule, and every brief brigade writes repeats it in its house rules.

## Commands

- `$brigade open` runs from any thread. It interviews the user with `grilling` for the menu and house rules, writes the store, then launches the head chef in the target project. In its first turn the head chef creates its own supplier, line-check, and close-out schedules, so each run posts into its own thread.
- `$brigade` inside a head chef thread is the operating manual: take tickets, group them, fire stations, run the pass, update the 86 board, write the close-out.
- `$brigade walk` prints every restaurant grouped under its repository, with the repository's landing status, each restaurant's counts, leases, and 86 board. It is a script, not an agent.

## Store

`${XDG_STATE_HOME:-~/.local/state}/pstack-t3/brigade/<project-slug>/<restaurant>/`

- `restaurant.json` records the name, project root, the head chef thread, schedule IDs, last activity, and last report. It records no landing mode. The repository's landing contract is the only record of the mode, and an old `landing` field is ignored.
- `menu.md`, `house-rules.md`: written from templates at opening, then edited by the head chef.
- `rail.tsv` (tickets), `dishes.tsv` (grouped work assigned to a station), `pass.tsv` (one verdict per dish and head SHA), `86.tsv` (decisions for the user): current state, updated in place.
- `log.tsv`: every state change, append-only.
- `closeouts/<timestamp>.md`: one report per close.
- `decisions.tsv`: owned by `show-me-your-work`.

The head chef thread is the only writer. Nothing is committed.

## Defaults

- `brigade.py dish <id> --state queued` and `--state merged` fail unless the dish has a `pass` verdict at its head SHA. The landing mode belongs to the repository's landing contract (`land.py init` and `land.py mode`). `brigade.py status` and `walk` read it from `land.py status`.
- `pass record` refuses a verifier from the author's model family unless `--same-family` is given, and then notes it on the verdict.
- A report lists only log entries after `lastReportAt`, so nothing the user already saw repeats.
- `walk` marks a restaurant idle after 24 hours without activity, so a stalled head chef shows up.

## Repo layout

- `t3/added/brigade/SKILL.md`
- `t3/added/brigade/scripts/brigade.py` with `open`, `ticket`, `fire`, `pass`, `86`, `close`, `walk`
- `tests/test_brigade.py`
- `docs/skills.md`, `README.md`, `CHANGELOG.md`

## Phases

0. Confirm T3 behavior. Done on 2026-10-04 with a probe thread launched into Bridgekit from the pstack-t3 project:
   - The launched thread ran in `full-access` and pinned itself with `t3_thread_organize`.
   - Its own `schedule_task` bound to it, and a forced run posted into its thread as a user message.
   - It delegated a child, read the child's thread, and saw the child in `t3_thread_list`.
   - The launching thread got `thread_not_found` from `t3_thread_read` on it. `t3_thread_read`, `t3_thread_send`, `t3_thread_list`, and `t3_thread_organize` only reach the calling project. So `$brigade open` hands off and never steers the head chef afterward. The user talks to the head chef in its own thread, and `walk` reads the store.
1. `brigade.py` and tests. Done: `t3/added/brigade/scripts/brigade.py`, `tests/test_brigade.py`.
2. `SKILL.md`, then fresh-child tests. Done. Two services ran on a scratch repo with a planted bug.
   - Codex as head chef: grouped two reports of one bug into one dish, dropped an off-menu ticket, had Grok fix it, reviewed it with Codex at the exact SHA, and fast-forwarded `main`.
   - Grok as head chef: fixed the empty-mean ticket, parked the empty-median policy as a decision with a default instead of asking, and dropped a feature request.
   - The tests found three defects, all fixed: the report repeated a dish under every state it passed through, ticket assignment was not logged, and the head chef had to read the script source because the skill listed only some commands.
3. Pilot one restaurant (Bridgekit) for a few services, then a second.
4. Docs and release.

## Pilot: Bridgekit performance, 2026-10-04

A head chef on Claude Opus 5.5 ran 5 dishes in 4.5 hours with 21 minutes of its own active time. 4 merged as PRs, 1 was dropped because no change beat the noise. Grok wrote every change. Codex and Claude reviewed them, and 2 of 6 reviews sent work back for real bugs. The landing queue had no conflicts or bounces. An audit of the head chef's thread found the problems below. Each change is in the CHANGELOG.

| Finding | Cost | Change |
| --- | --- | --- |
| 3 of 8 worker runs stayed open after the worker wrote its report, so no completion notice woke the head chef | 31 to 53 minutes idle each, found only when the user asked for status | Workers are worktree threads. A liveness schedule runs `brigade.py watch`, which flags a written report or an overrun timebox. |
| Subagent workers were invisible to the user and one died in a T3 restart | Status questions from the user, one lost run | Worktree threads show in the sidebar and survive restarts. Reviewers stay subagents: 6 of 6 closed normally in 2 to 12 minutes. |
| The baseline was measured while other workers ran | `perf/baseline.json` reads about 20% slow | `land.py slot --exclusive`, added to every measuring station's brief |
| A hand-assembled brief left a placeholder | One worker cancelled and respawned | `brigade.py brief` assembles and checks every field |
| The lease was claimed before the dish had an ID | Ordering ambiguity in the skill | `brigade.py fire --paths` claims the lease first |
| The queue's PR text was rewritten by hand 4 times | 4 extra `gh pr edit` calls | `land.py submit --title --body-file` |
| One decision repeated as "still open" in 8 replies | Noise | Raise once, then only in reports |
| "Clean up branches" deleted 4 user branches | Broader than asked | Delete only branches the restaurant created |
| Doubled log entries | Cosmetic | Log a state only when it changes |
