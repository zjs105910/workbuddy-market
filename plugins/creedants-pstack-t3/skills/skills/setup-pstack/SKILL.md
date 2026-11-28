---
name: setup-pstack
description: Configure which T3 providers and models pstack uses per role, at what reasoning budget, and whether mode is full or light. Reads the live T3 catalog and writes a roles file that every pstack skill reads. Use for /setup-pstack, "configure pstack models", "pstack budget", "pstack mode", or changing pstack's model choices.
---

# Setup pstack

Read [the pstack-t3 runtime](../pstack-runtime/SKILL.md) before spawning workers, choosing models, scheduling, or isolating work. It maps those steps onto T3's orchestrator tools.

Write `~/.config/pstack-t3/roles.json`, the per-role seat table that every pstack-t3 skill reads through [the runtime](../pstack-runtime/SKILL.md). A project can override roles in `.pstack/t3-roles.json`.

`<runtime>` below is the `pstack-runtime` skill directory next to this one.

## Steps

### 1. Check the host and read the catalog

Check the host's tool list for `watch_pull_request`. Accept the T3 harness prefixes described in [the runtime](../pstack-runtime/SKILL.md). A tool listed by name counts as present, including a harness prefix. A deferred `watch_pull_request` counts as present and does not fail this gate. If tools load lazily, use the host's tool discovery and make one bounded `orchestrator_capabilities` call before checking again. A provider catalog does not prove that the watch tool exists. Do not call `watch_pull_request` with a dummy PR to test it.

If `watch_pull_request` is absent, stop setup before writing roles or a saved catalog. Say "Setup cannot finish. T3 Code 0.0.46-nightly.20261005.2702 or later is required because this host does not expose watch_pull_request." Ask the user to update T3 Code and rerun setup. Do not report setup complete.

Call `orchestrator_capabilities`. Save its JSON result verbatim to a temporary file, for example `/tmp/pstack-t3-catalog.json`. That file is the only source of valid providers, models, and options. Never write a seat that is not in it. Keep the file for the commands in this skill. `show` and `write` both read it, and a user-level `write` saves a copy as the snapshot. A skill that only resolves a role from a tool result uses the quoted heredoc in [Where roles live](../pstack-runtime/SKILL.md#where-roles-live) instead of a file.

List the runnable providers (`canRunChildTask: true`) with their first three models. List the providers that are not runnable with their `constraints`, such as "Provider is not authenticated", so the user knows what to fix in T3 settings. Muse is beta and disabled by default. Its status can come from a cached catalog without a login or model check, so `canRunChildTask: true` does not prove a Muse seat works. Step 5's smoke delegation decides it. Match a Muse instance by `driverKind: "muse"`, not by the ID `muse`.

### 2. Load current state

```bash
python3 <runtime>/scripts/roles.py show --cwd "$PWD" --catalog /tmp/pstack-t3-catalog.json
```

This prints every role with its seats and `source` (`default`, the user file, or the project file), already resolved against the catalog. It also prints `mode`, `modeSource`, and `escalate`. `notes` name seats that no longer match, such as a model T3 dropped. A saved `contextWindow` on a native Claude 5 seat shows as `dropped unknown options contextWindow`, because T3 Code 0.0.46-nightly.20261008.2801 fixed those models at 1M context. Rewrite that seat without it in step 4.

When a `claude-opus-5-5`, `claude-sonnet-5-5`, or `claude-haiku-5-5` seat is missing on a native Claude provider, look at T3's model picker for an update notice that names the Claude Code version that model needs. If the notice is there, tell the user to update Claude Code in T3's provider settings and rerun setup. Do not seat a replacement family without saying so.

### 3. Budget, map, and confirm

**(a) Ask for a budget.** Use the host's question tool if it has one. Offer these labels, and name the current budget.

- `default — built-in role reasoning or configured seat options`
- `unlimited — max reasoning`
- `large — xhigh reasoning`
- `medium — high reasoning`
- `small — medium reasoning`

The budget caps the reasoning option (`effort`, `reasoningEffort`, `reasoning_effort`, or `reasoning`). A seat at or below the cap keeps its level. A seat above the cap drops to the cap, or the closest lower level the model offers. A seat that names no level receives the cap. `default` leaves a built-in or configured level as it is. The ladder stops at max. `unlimited` raises the built-in Opus and Grok seats to the model's highest level at or below max. It does not raise the Claude Haiku 5.5 seats. The default Opus seat moves from xhigh to max. Grok's ladder tops out at xhigh, so the default Grok seat stays at xhigh. `unlimited` lowers a configured `ultra` seat to max when the model offers a level at or below max. `default` keeps a configured `ultra` seat. When every offered level is above the cap, the seat gets the lowest level. A configured seat that names its own level keeps that level when it is at or below the cap. A model without such an option is unaffected. `ultracode` and `ultrathink` are never set by a budget.

**Ask for a mode.** Use the host's question tool. Name the current `mode` and `modeSource` from step 2. Offer these options, in this order.

- `full — recommended when no provider is near its limit`
- `light`

Store the chosen value beside the budget. When the write target is the project file, name the current `escalate` from `show`. `null` means none. Suggest `**/migrations/**` plus that repository's own lock and installer scripts. In this repository those scripts are `t3/added/landing/scripts/land.py`, `t3/added/brigade/scripts/brigade.py`, and `scripts/install.py`. Do not suggest those three paths for any other repository. Pass one `--escalate` per pattern the user keeps. Omitting both escalate flags leaves a stored project list in place. `--clear-escalate` removes it.

**(b) Propose roles.** The built-in defaults are Claude Opus (`claude-opus-5-5`) at xhigh for judgment roles and Grok (`grok-4.7`) at xhigh for code roles. Under `unlimited`, those seats rise as step 3(a) describes. Opus moves to max, and Grok stays at xhigh. `arena runners`, `arena cross-judge pool`, `architect runners`, and `interrogate reviewers` use those two seats, judgment first. `skill tests` uses Claude Haiku 5.5 at high. `verifiers` stays on its built-in panel rule. `review backups` is optional and has no built-in seats. Leave it unset unless the user names a panel. When set, a `verifiers` seat whose paid backups are all out runs that panel instead of parking. Never propose a Cursor, Codex, or `inherit` seat for it. `write` refuses a Cursor or Codex seat in this role unless `--force` is passed. Start from `roles.py show` in step 2. Keep configured roles unless the user changes them. Use the built-in seats for roles with `source: "default"`. Offer `large` for a new setup. It matches the built-in xhigh ceiling. Show each fallback note beside its role and seat. Codex and every other runnable configured provider remain available as user choices. Leave `skill tests` unset so it keeps the built-in Haiku default. `how explorer` and `why investigators` also default to Claude Haiku 5.5 at medium. Never write Claude Haiku 4.5 or a fast Grok id. `write` refuses excluded seats, even with `--force`, per [the runtime's Excluded seats](../pstack-runtime/SKILL.md#excluded-seats).

**(c) Confirm.** Show every role with its seats. Ask whether to accept as-is or change specific roles. For panel roles the seat count is the panel size.

### 4. Write

Build one `--set` per role you are writing. A seat is `inherit` or `provider/model`, with options as a query string. Separate panel seats with `;`.

```bash
python3 <runtime>/scripts/roles.py write --catalog /tmp/pstack-t3-catalog.json --budget large --mode full \
  --set "judgment and prose=claudeAgent/claude-opus-5-5?effort=xhigh" \
  --set "swarm workers=grok/grok-4.7?reasoningEffort=xhigh" \
  --set "interrogate reviewers=claudeAgent/claude-opus-5-5?effort=xhigh;grok/grok-4.7?reasoningEffort=xhigh"
```

The provider, model, and option IDs above are examples. Use IDs from step 1. Never write a fast Grok id such as `grok-4.7-build-fast`, or `fastMode=true` on a Grok seat. `write` refuses both, even with `--force`, and `validate` reports both. Leave `fastMode` out. `roles.py` pins a declared Grok `fastMode` to `false`, never picks or inherits a fast Grok seat, and refuses a parent whose `fastMode` it cannot pin, per [the runtime's Excluded seats](../pstack-runtime/SKILL.md#excluded-seats). Write `contextWindow` only for a model whose catalog entry offers it. Cursor's Claude 5 models still offer it. T3's native Claude 5 models do not.

- The command overwrites the whole file, so re-runs are idempotent. Add `--keep` to keep roles you did not pass. A user write without `--mode` stores `full`. A project write without `--mode` omits the key. Omitting `--escalate` leaves a stored project list in place.
- With no excluded seat, it runs `validate`'s checks on the roles it is about to store. When they list a problem, it prints each one and writes nothing unless `--force` is passed. Fix each problem and rerun. Do not pass `--force` unless the user asks.
- Add `--project` to write `.pstack/t3-roles.json` for this repository instead.
- A user-level write also saves the catalog snapshot to `~/.config/pstack-t3/catalog.json`, which `roles.py show` uses later to resolve fallbacks.

### 5. Verify

Run `python3 <runtime>/scripts/roles.py show --cwd "$PWD" --parent "<inheritedProviderInstanceId>/<inheritedModel>"`. Check that configured seats resolve with no mismatch notes. For unset roles, review and report each default fallback note. A default fallback does not invalidate an otherwise runnable setup. `info` lines, such as an `inherit` seat made explicit for the budget, are expected. Then run one smoke delegation to each distinct provider in the table: `delegate_task` with `mode: "wait"`, `timeoutMs: 120000`, the seat's target, and the task "Reply with the single word ready." A seat that fails here is not usable. Fix it and rerun step 4. The smoke task runs no command, so it does not prove a Muse child can work under this thread's runtime mode. Check that per [Permissions](../pstack-runtime/SKILL.md#permissions).

### 6. Confirm

Do this only after step 1 found `watch_pull_request` and step 5's smoke delegations succeeded. Tell the user which file was written, the budget, the mode, any provider they could enable in T3 settings to widen `verifiers`, and that new sessions pick it up immediately. Re-running this skill updates it.

### 7. Offer a verification skill (optional)

Check whether the project has a way to drive the real app for proof, such as a `verify-*` skill or an existing harness. If not, offer once: "want a project-local verification skill, so agents can drive the app the way a user does and prove changes work? I can generate one with /create-verification-skill." On yes, invoke `create-verification-skill`. On no, move on.
