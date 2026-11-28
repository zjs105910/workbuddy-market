# Working on pstack-t3

pstack-t3 is Lauren Tan's pstack, ported to run natively in T3 Code on any provider through T3's orchestrator V2 tools.

## Layout

- `vendor/pstack/` is upstream, byte-identical to the commit in `upstream.json`. Never edit it. `scripts/sync_upstream.py` replaces it.
- `t3/runtime.md` becomes `skills/pstack-runtime/SKILL.md`. It is the single contract for delegation, roles, isolation, scheduling, verification, history, and PR linking. Skills link to it instead of restating it.
- `t3/scripts/roles.py` resolves roles to `delegate_task` targets. Tests in `tests/`.
- `t3/setup.md` becomes `skills/setup-pstack/SKILL.md`.
- `t3/overrides/<skill>/<path>` replaces `vendor/pstack/skills/<skill>/<path>` wholesale.
- `t3/added/<skill>/<path>` adds files upstream lacks.
- `t3/removed.txt` lists upstream paths pstack-t3 does not ship.
- `t3/agents/` holds the personas copied into `skills/pstack-runtime/agents/`.
- `skills/` is generated. Never edit it by hand. Run `python3 scripts/build.py`.

## Porting an upstream file

Start from the upstream file and change only what T3 changes. Upstream's rules, steps, voice, and rigor carry over unchanged. A port that rewrites the engineering content is a regression.

1. Copy `vendor/pstack/skills/<path>` to `t3/overrides/<path>`.
2. Replace each Cursor mechanism with its T3 equivalent from `t3/runtime.md`:
   - `Task` calls, `subagent_type`, `run_in_background`, `readonly`, `environment: "cloud"`, `cloud_base_branch` become `delegate_task` with `mode: "async"`, a `role`, a resolved `target`, and a read-only brief where upstream said `readonly`.
   - A model line in `~/.cursor/rules/pstack-models.mdc` becomes "the `<role>` role" resolved per the runtime's Roles section. Delete hard-coded slug defaults and family-prefix fallback rules. The runtime's defaults and fallback replace them.
   - `inherit-parent` or `auto` becomes `inherit`.
   - `/loop`, automations, hourly ticks, and scheduled wakeups become `schedule_task` when they are a cadence with no pull request event.
   - A wait on a pull request's checks, reviews, or conflicts, including `scripts/watch-pr` and a poll loop, becomes `watch_pull_request` on the thread that owns the pull request.
   - A wait whose predicate is the merge also keeps the `schedule_task` heartbeat the runtime's Pull request watching section requires.
   - Cloud agents become child tasks. Long-lived PR owners and coordinator-visible owners become `t3_thread_launch` threads with a worktree strategy.
   - Transcripts and cloud-agent URLs become T3 threads read with `t3_thread_search` and `t3_thread_read`.
   - `control-ui` becomes T3 preview tools. `control-cli` becomes driving the CLI in the terminal.
   - `AskQuestion` becomes the host's question tool.
   - Cursor's `create-skill` becomes the `pstack-author-skill` skill.
   - `cursor-team-kit` skills (`deslop`, `control-ui`, `control-cli`) become "if installed" with a stated fallback.
   - After opening or driving a PR, add the `link_pull_request` step.
3. Link the runtime by relative path (`../pstack-runtime/SKILL.md` from a SKILL.md, `../../pstack-runtime/SKILL.md` from a playbook) when the step needs it. Do not paste runtime content.
4. Keep tool names unprefixed (`delegate_task`, not `mcp__t3-code__delegate_task`).
5. Run `python3 scripts/build.py`. The build fails on Cursor leftovers (see `scripts/check.py`), broken links, bad frontmatter, or override drift.
6. Run `python3 scripts/build.py --update-lock` only after reviewing that the override matches the current upstream file.

## Writing style

Follow upstream's: short declarative sentences, no long dashes, no mid-sentence colons, no hedging. Every instruction names a concrete tool, path, or check.

## Tests

```bash
python3 -m unittest discover -s tests -v
python3 scripts/build.py
```

Never commit credentials, transcripts, local configs, catalog snapshots, or thread IDs.
