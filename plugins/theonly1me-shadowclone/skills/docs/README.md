# Documentation

Start with the [README](../README.md) to install Shadowclone and pick your first skills.

## Guides

- [Agent builds](guides/agent-builds.md): pick skills and a build scope.
- [Learning](guides/learning.md): run deep or background learning, or record a rule.
- [Skill maintenance](guides/skills.md): review updates and conflicts, and undo a change.
- [Repository setup](guides/repositories.md): share checks and skills with a repository.
- [Pi setup](guides/pi.md): use Pi models, including local models.
- [Delegated work](guides/delegated-work.md): take a change to ready for review.
- [Cloud bot](guides/cloud-bot.md): set up a GitHub bot.
- [Reviews](guides/reviews.md): review a pull request on your machine or in the cloud.
- [MCP server](guides/mcp.md): give a connected agent the Shadowclone tools.
- [Command reference](guides/commands.md): find every command.
- [Migration](guides/migration.md): move a profile installation to skills.
- [Enterprise controls](guides/enterprise.md): set scope and managed policy.

## Privacy and results

- [Privacy](../PRIVACY.md), [data handling](data-handling.md), and [security](../SECURITY.md): what Shadowclone reads, sends, stores, and removes, and how to report a vulnerability.
- [Evaluation results](../evals.md): preference adherence for five setups and four models.

## Understand and contribute

- [Motivation](motivation.md): why the project exists.
- [Architecture](architecture/README.md): packages, dependencies, data flow, and trust boundaries.
- [Design history](design/README.md): decisions, and the designs that replaced them.
- [Evaluations](../evals/README.md): the suites and paid runs.
- [Contributing](../CONTRIBUTING.md): setup, checks, new packages, and pull requests.

Coding assistants start with [AGENTS.md](../AGENTS.md). Each package also has an `AGENTS.md`.

## Open work

- Test setup, migration, conflict recovery, and removal on real installations with explicit source consent.
- Measure whether maintained guidance reduces the effort of repeated tasks. Preference scores do not measure productivity.
- Add a model runner for Antigravity, which has capture and native guidance only. No API or local-endpoint engine exists.
- Define evidence and action boundaries for merge outcomes, issue-tracker intake, and concurrent clones. The learning workflow excludes them.
