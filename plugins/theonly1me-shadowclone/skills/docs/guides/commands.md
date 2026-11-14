# Command reference

Run `shadowclone --help` for the full command shape. Run `shadowclone` with no arguments to see the current result and the next step.

## Set up

- `shadowclone init`: choose consent for learning and skill maintenance.
- `shadowclone init --advanced`: choose each capture source on its own.
- `shadowclone init --status --json`: check whether setup exists, with no change.
- `shadowclone init --repo`: set up shared instructions, skills, and checks for this repository.
- `shadowclone wizard`: pick skills in the browser. `--repo` opens it for this repository, `--no-open` prints the local URL, and `--cli` configures a build in the terminal.
- `shadowclone install --agent all --global`: install native guidance for every agent. `--agent <agent> --local` installs it for this repository only.
- `shadowclone uninstall --global` or `--local`: remove the integrations that Shadowclone owns in that scope.
- `shadowclone sync`: refresh maintained skills, bundled skills, and native routing.
- `shadowclone doctor`: check the installation and the effective policy.
- `shadowclone forget --all`: remove all Shadowclone state and the files that it owns.

Agent identifiers are `claude-code`, `codex`, `cursor`, `antigravity`, and `pi`. Add `--subagent` to install an optional local Claude subagent. Add `--auto-delegate` to allow automatic delegation.

## Learn

- `shadowclone learn`: index sessions and report, with no model call.
- `shadowclone learn --deep`: run a bounded learning pass with a model. Options are `--dry-run`, `--apply`, `--engine <id>`, `--model <id>`, `--reasoning-effort <level>`, and `--max-calls <n>`. See [learning](learning.md).
- `shadowclone remember [--repo or --global] <text>`: record a rule yourself.
- `shadowclone import`: read consented repository guidance as evidence.
- `shadowclone recall <query> [--limit 1..10]`: search the scoped reference records.
- `shadowclone learning enable`, `disable`, or `status`: turn background learning on or off, or read the last attempt.
- `shadowclone learning list` or `pending`: list active guidance, or every open review and publication decision.
- `shadowclone learning show <key>`: read the redacted evidence, the guidance, and the scope.
- `shadowclone learning apply <key>` or `reject <key>`: decide a learned rule.
- `shadowclone learning retire <key>`, `narrow <key>`, or `replace <key> <guidance>`: preview a retirement, a limit to this repository, or a replacement.
- `shadowclone learning remove-source <source>`: preview the removal of guidance that one source alone supports.
- `shadowclone learning repositories` and `bind <id>`: review and confirm repository links for past sessions.
- `shadowclone learning acknowledge <key>`: mark later corrections as reviewed.
- `shadowclone learning probe <key> --agent <agent> --task <text> --expect <text> --yes`: test one exact response on macOS. `probe status` reads the last receipt.

## Skills, context, and history

- `shadowclone skills`: list the bundled skills. `skills list` lists the skills in your configured roots.
- `shadowclone skills update`: review the library and update skills.
- `shadowclone skills pending`: list unpublished learning and conflicts.
- `shadowclone skills show <id>`, `apply <id>`, or `reject <id>`: decide a proposal.
- `shadowclone skills configure [--repo or --global]`: choose the skill roots to maintain. It also accepts `--root <directory>` and `--third-party`.
- `shadowclone skills automatic on` or `off`: allow or stop automatic edits.
- `shadowclone skills retry <key>` or `exclude <key> <reason>`: queue a record again, or keep it unpublished.
- `shadowclone skills disable`: stop access to the skill library.
- `shadowclone context --explain`: show the guidance that is active in this repository.
- `shadowclone history [revision]`: list revisions, or show one.
- `shadowclone undo <revision>`: restore the files of a revision.

See [skill maintenance](skills.md).

## Review, cloud, and repository

- `shadowclone review <pr>`: review a pull request on this machine and write a Markdown file. `--base <ref>` reviews the commits on this branch since it left `<ref>`. `--cloud` asks the cloud bot instead. Other options are `--no-checks`, `--offline`, `--repo owner/repository`, `--output file.md`, `--model <id>`, and `--effort <level>`. The cloud workflow also uses `review prepare`, `checks`, `analyze`, and `publish`. See [reviews](reviews.md).
- `shadowclone bot setup`: open the browser setup, which also offers a GitHub App. `--bot <login>` sets up a machine account bot, and `--app` selects a GitHub App. The two options exclude each other. Other options are `--engine claude` or `codex`, `--codex-auth api-key` or `plan`, `--repo owner/repository`, `--yes`, and `--no-open`. See the [cloud bot guide](cloud-bot.md).
- `shadowclone bot status [--repo owner/repository]`: show the setup steps that are still open.
- `shadowclone bot export --skill <name> --output <private-folder>`: save skills to a folder outside the checkout, with no upload.
- `shadowclone check [--changed]`: run the repository checks. `--format` accepts `human`, `json`, or `claude-stop`.

## Migrate and serve

- `shadowclone migrate skills`: preview a move from a profile installation to skills.
- `shadowclone migrate claude-memory`: preview the older one-time import of Claude memory.
- `shadowclone profile repair`: preview repairs for a profile installation.
- `shadowclone mcp`: serve the [MCP tools](mcp.md) on standard input and output.

## Install notes

A repository install adds each file that it creates to `.git/info/exclude`, so the files stay out of commits. Uninstall removes those entries.

If an agent's instruction file links to a regular file in your home folder, Shadowclone keeps the link and writes its block into that file. If `~/.claude/CLAUDE.md` imports the same file with `@`, Claude Code gets no second block. Shadowclone follows no other link. Setup skips that agent, installs the others, and names the link and its target. `shadowclone install --agent <agent>` fails on such a link until you replace it with a regular file.

A Codex repository install writes `AGENTS.override.md`. Codex reads one instruction file in each folder, so the override would hide an existing `AGENTS.md`. In that case the install skips Codex, names both files, and exits with status 1. Other agents still install. Run `shadowclone install --agent codex --global` instead. If an earlier version created the override, the install says so and explains how to remove it.

## Non-interactive setup

An agent can pass all three consent decisions without prompts:

```bash
shadowclone init --learn --skill-maintenance --background-learning
```

Each flag has a `--no-` form. If you pass one consent flag, you must pass all three. Background learning needs session learning. An incomplete command exits and writes no configuration.
