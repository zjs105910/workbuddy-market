# opencode-planning-with-files

Native [OpenCode](https://opencode.ai) plugin for [planning-with-files](https://github.com/OthmanAdi/planning-with-files): persistent file-based planning for AI coding agents. The plan lives on disk in `task_plan.md`, `findings.md` and `progress.md`; this plugin keeps it in the model's context on every turn and can hold the session open until the plan reports complete.

## Install

Version 1.2.0 supports OpenCode 1.18.21 and OpenCode 2.0.21. For OpenCode 2, add the plugin to `opencode.json` (project) or `~/.config/opencode/opencode.json` (global):

```json
{
  "plugins": ["opencode-planning-with-files@1.2.0"]
}
```

OpenCode 1 uses the singular `plugin` key:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": ["opencode-planning-with-files@1.2.0"]
}
```

OpenCode installs the package on the next start. Install the skill text as well so the agent knows the workflow:

```bash
npx skills add OthmanAdi/planning-with-files --skill planning-with-files -g
```

That command lands in `~/.agents/skills/planning-with-files/`, one of the paths OpenCode reads natively.

## What the plugin does

| Behavior | OpenCode 2 | OpenCode 1 |
|---|---|---|
| Inject framed planning context | `session.hook("context")`, added to the model request | `chat.message`, added as a synthetic message part |
| Remind after writes | `tool.hook("execute.after")`, preserving output and attachments | `tool.execute.after` |
| Preserve the plan pointer and hash during compaction | `session.hook("compaction")` | `experimental.session.compacting` |
| Continue an unfinished gated plan | `session.status` with an `idle` status | `session.idle` |
| Planning tools | `tool.transform` | `tool` definitions |

The tools are `pwf_init` (root or `.planning/<date>-<slug>/`, `mode: autonomous` or `gated` with attestation), `pwf_status` and `pwf_check`. Write reminders apply to `write`, `edit`, `patch`, `multiedit` and `apply_patch`.

Plan selection honors `PLAN_ID`. Without it, multiple named plans produce an ambiguity notice; a single named plan or the legacy root plan can be selected. The completion gate uses `PWF_GATE_CAP` (default 20) and ledger stall detection to release the session. Child sessions are never re-prompted.

Local v2 wrappers must re-export the default definition: `export { default } from "./path/to/dist/index.js"`. The default definition also carries the v1 `server` entry, and the named `PlanningWithFiles` factory remains available.

Autonomous and gated plans inject only when `.attestation` (slug) or `.plan-attestation` (root) matches the SHA-256 of `task_plan.md`. `PLANNING_DISABLED=1` silences every hook; `PWF_PLAN_ROOT=<absolute path>` pins the project root and fails closed when it does not resolve. A live plan in a direct child project makes a cwd guess ambiguous and nothing is injected, with a one-line notice.

## Commands

Copy `pwf.md` and `pwf-status.md` from the repository's `.opencode/commands/` into `~/.config/opencode/commands/` (or your project's `.opencode/commands/`) to get `/pwf [--gated] [plan name]` and `/pwf-status`.

Full guide: [docs/opencode.md](https://github.com/OthmanAdi/planning-with-files/blob/master/docs/opencode.md).

## License

MIT
