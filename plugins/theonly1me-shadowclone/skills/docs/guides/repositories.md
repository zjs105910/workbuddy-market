# Repository setup

Use `shadowclone init --repo` to share instructions, skills, and checks with everyone who works in a repository.

## Set up the repository

```bash
shadowclone init --repo
```

Setup asks to read the project manifests, finds the checks, and previews the shared instructions and workflow skills. It asks again before it adds personal preferences to shared files. Commit the files that you want to share.

- `AGENTS.md` holds shared instructions, selected skills, and verification commands.
- `CLAUDE.md` imports the shared instructions.
- `.agents/skills/` and `.claude/skills/` hold repository workflows and selected personal skills.
- `.shadowclone/harness.json` holds configured checks, conventions, and file fingerprints.

`--personal` or `--no-personal` includes or excludes your applicable personal guidance. Repeat `--skill <name>` to copy selected personal skills with their resources. `--no-enforce` skips the Claude Stop hook.

For a shared skill build, use the **Shared · this repository** scope ([Agent builds](agent-builds.md#choose-a-build-scope)).

## Check and refresh

Run `shadowclone check --changed` to check your uncommitted work, or `shadowclone check` for the whole repository. A local Claude Stop hook runs these checks before the agent finishes. Other agents get the checks through the repository instructions.

`shadowclone sync` refreshes the setup. Your text outside the managed sections stays yours, and Shadowclone keeps an edited managed section for your review. A skill left out of the routing can still reach an agent through its global configuration.
