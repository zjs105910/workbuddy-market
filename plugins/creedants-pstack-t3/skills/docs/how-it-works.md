# How it works

pstack-t3 has three layers. T3 Code supplies the orchestration tools. The `pstack-runtime` skill explains how to use them. The other skills decide when and why.

```mermaid
flowchart TD
    you["You: $interrogate review this branch"] --> lead["Lead thread<br/>any provider: Claude, Codex, Grok, Cursor"]
    lead -->|reads| skill["interrogate skill<br/>what to do: intent, panel, rubric, synthesis"]
    skill -->|links| runtime["pstack-runtime skill<br/>how to do it in T3"]
    runtime --> caps["orchestrator_capabilities<br/>which providers and models exist now"]
    runtime --> roles["roles.py<br/>role to seats, budget, fallbacks"]
    caps --> roles
    roles --> fan{"one delegate_task per seat"}
    fan --> a["Reviewer A<br/>Claude Opus"]
    fan --> b["Reviewer B<br/>Grok"]
    a & b -->|completion wakes the lead| synth["Lead verifies each claim,<br/>weighs cross-family agreement,<br/>writes one verdict"]
```

## The layers

**T3 Code's orchestrator V2.** Every provider T3 runs gets the same `t3-code` tools. `delegate_task` starts a child agent on a chosen provider and model. `orchestrator_capabilities` lists what is available. `t3_thread_launch` starts a separate thread, optionally in its own git worktree. `schedule_task` runs recurring work. `t3_thread_read` reads past threads. The `preview_*` tools drive a browser. `link_pull_request` tracks PRs.

**`pstack-runtime`.** One skill that maps every pstack concept onto those tools. It covers how to delegate, how to pick models, how to isolate writers, how to schedule, how to verify, and how to handle failures. Other skills link to it instead of repeating it. Read it in [`t3/runtime.md`](../t3/runtime.md).

**The skills.** Lauren Tan's engineering workflows: when to fan out, what a worker's brief must contain, how to verify, and how to merge results. They are upstream's text, with only the Cursor mechanics replaced.

## Roles and models

pstack never hard-codes a model. Each step names a role, and `roles.py` resolves that role against T3's live catalog.

| Role kind | Default |
| --- | --- |
| Single seat (`bug-fix`, `judgment and prose`, `swarm workers`, ...) | Unset single roles use Claude Opus (`claude-opus-5-5`) at xhigh for judgment and Grok (`grok-4.7`) at xhigh for code. `skill tests` prefers a model from another family for a fresh-child skill test. |
| `arena runners`, `arena cross-judge pool`, `architect runners`, `interrogate reviewers` | Those two seats, Claude Opus then Grok |
| `verifiers` | This thread's model plus one seat per other model family you can run. With one runnable model family, `verifiers` is three copies of one seat. That seat is this thread's model only when this thread's provider can run children. Otherwise that seat is the runnable provider's first model. |

`$setup-pstack` writes your own choices to `~/.config/pstack-t3/roles.json`. A repository can override roles in `.pstack/t3-roles.json`. A reasoning budget (`small` to `unlimited`) sets each seat's effort. A seat whose model you cannot run falls back, and the report names each replacement.

Diversity is counted by model family, not by provider, because one provider can serve another's models. Cursor can run Claude, for example.

## Where work runs

| Work | Runs as |
| --- | --- |
| Reviewers, investigators, read-only workers | Child tasks sharing the lead's checkout |
| Writers that could collide | Child tasks in a git worktree the lead creates |
| Long-lived owners (Autopilot, Orchestrate) | Separate T3 threads bound to their own worktree |
| Overnight and recurring checks | `schedule_task` |
| A standing coordinator (`$brigade`) | A pinned thread on the project root. It never writes code. Each unit runs in its own worktree thread. |
| An executive admin (`$brigade-admin`, optional) | A pinned thread on the project root. It serves every coordinator on one repository. It routes your requests and owns shared intake. It settles conflicts between coordinators by published rules. You can overrule any ruling. `land.py` reservations, shares, and contests carry out its rulings. It never runs work. See [An executive admin](guide.md#an-executive-admin). |
| The landing queue (`$landing`) | One queue per repository. `land.py land` is the only writer to trunk. See [Landing modes](guide.md#landing-modes). |

The lead ends its turn while children work. T3 wakes it as each one finishes. A coordinator's worker calls `t3_thread_send` on the coordinator thread as its last step, after the report file is written. That report-back wakes the coordinator. The liveness check runs while work is in progress, every 10 minutes at `every-turn` and `milestones` and every 30 minutes at `digest`. `brigade.py watch` prints `report written, no report-back` while the work is in progress, when the report was written for this attempt, and when this attempt is not marked reported. The report counts as written for this attempt when its modification time is at or after the attempt's start. A report left by a replaced worker does not count. That line is a defect. The check reads the worker's activity, finds the cause, and fires a fix at that cause.

## How a coordinator reports

The level is chosen when the coordinator opens. `brigade.py set --reporting` changes it later. The stored values are `every-turn`, `milestones`, and `digest`. The default is `milestones`. A `restaurant.json` with no `reporting` field reads as `milestones`.

`every-turn` sends a short reply after every wake. `milestones` replies when work merges, a review sends work back or blocks it, a decision needs you, something fails or the queue pauses, or you send a message. A liveness check with nothing new, a liveness check while a review is pending, a review starting, and a worker launching are routine. At `milestones`, a routine wake ends with no reply, or with one line when the host requires text. `digest` replies only for a decision you must make, a failure or a paused queue the coordinator cannot fix itself, one summary when a batch drains, the 18:00 report, and a message from you. Every other wake ends with no reply text at all, not even a status line. That includes a worker reporting back, a review starting or finishing, a send-back, a worker launching, a merge that leaves work in progress, in review, passed review, or waiting to land, a pull request wake, a liveness check, intake with nothing new, and a schedule created, recreated, or deleted. A `digest` message is a few plain sentences for a person on what got done, what comes next, and what you must decide. It carries no work or ticket IDs, SHAs, file paths, review-round counts, or tool names. Merged pull requests may follow as a short list of linked plain titles. `brigade.py close --to-file` writes the full report, and the message names its path in one line instead of pasting it.

Every level sends the 18:00 report. The 09:00 run is not a report. A message from you gets at least one line, and a direct question gets an answer. The [guide](guide.md#reporting-levels) walks through the same choice. A missing report-back is a defect. The liveness check fires a fix at its cause.

## How work lands

A writer claims a lease on the paths it will change before it starts. An overlapping claim is refused. The writer commits in its own worktree and stops. It never merges, rebases a shared branch, or pushes trunk. A reviewer from another model family checks that exact commit. The queue lands that commit, and bounces it when the rebased result differs from the reviewed one. Whoever runs `land.py land` while the lock is free drains the queue. Builds and tests run under `land.py slot`, which limits how many heavy commands run at once.

The mode is one per repository. It decides what reaches trunk and whether you are a gate. The four modes are in [Landing modes](guide.md#landing-modes).

## How the repository is built

```mermaid
flowchart LR
    up["vendor/pstack<br/>upstream, untouched"] --> build["scripts/build.py"]
    t3["t3/<br/>runtime, setup, overrides"] --> build
    build --> check["scripts/check.py<br/>no Cursor leftovers,<br/>valid frontmatter, links"]
    check --> skills["skills/<br/>what gets installed"]
    skills --> install["scripts/install.py"]
    install --> dirs["~/.claude/skills  ~/.agents/skills<br/>~/.grok/skills  ~/.cursor/skills"]
```

- `vendor/pstack` stays byte-identical to the upstream commit in [`upstream.json`](../upstream.json).
- `t3/overrides/` replaces individual upstream files. A lock file records which upstream version each override came from, so a newer upstream flags exactly the files that need re-porting.
- The build fails if any installed file still mentions a Cursor-only mechanism, such as `subagent_type`, `/loop`, or a hard-coded Cursor model slug.
