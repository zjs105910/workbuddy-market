# Simpler, agent-led setup and bounded first learning

## Problem

Initial setup asked too many detailed questions before producing useful guidance. Spawned Claude subagents could miss live context. Setup or evaluation work could outlast a reasonable first run.

Installing the plugin also required users to install and configure the CLI themselves. A plugin could activate bundled skills before the user chose them. Non-interactive setup could not express the three consent decisions safely.

## Decision

Use a short default setup that covers source access, skill maintenance, and background learning. Advanced mode offers detailed source selection. After consent, allow a first learning pass capped at 12 calls and 90 seconds, with a $1 ceiling where supported.

Deliver scoped context to spawned Claude agents through `SubagentStart` as well as the main-session path. Keep existing hook configuration. Keep session attribution separate from the guidance that Shadowclone supplies.

Publish a dedicated plugin whose only active skill is `setup-shadowclone`. The skill does these steps:

1. Detect whether the CLI and configuration exist.
2. If needed, install the public CLI without elevated privileges.
3. Ask separately about session learning, skill maintenance, and background learning.
4. Pass all three decisions as explicit flags.
5. Install the detected supported agents.
6. Start the loopback wizard without opening a browser.
7. Give the local URL to the user.
8. After the user applies a build, run synchronization, diagnostics, and context checks.
9. Ask the user to restart their agent.

Keep the distributable plugin below `plugins/shadowclone`. Then the repository's seed skill library cannot activate during plugin installation. Publish portable, Claude, and Codex manifests and the MCP configuration from that directory. Point both marketplaces to it. Keep manifest versions synchronized with the CLI release.

Support `shadowclone init --status --json` for read-only detection. Support the explicit consent flags `--learn`, `--skill-maintenance`, and `--background-learning`, each with a matching negative form. Any explicit consent flag requires all three decisions. In a non-interactive process, incomplete consent exits without writing configuration. Background learning requires session learning. The command keeps existing configuration.

Serialize reconciliation where concurrent writers could lose changes. Evaluate from frozen snapshots, so later learning or user edits cannot change a comparison during a run. Set limits on task generation, candidate execution, and judging. When a run reaches a limit, keep the recoverable results.

## Verification

Test the default and advanced setup paths, cancellation, first-pass limits, concurrent updates, and main-agent and subagent delivery. Synthetic and live checks establish only the behavior that they test. Successful setup or a completed evaluation does not establish a productivity gain.

Package and validate the nested plugin for Claude, Codex, Cursor, Antigravity, and agents that can follow a portable setup skill. Test status output, complete and incomplete consent flags, invalid consent combinations, non-interactive behavior, and the preservation of existing configuration. Run the security scanner with a minimum score of 90. Fail the run on medium or higher findings.

[Agent builds](024-agent-builds.md) describes the browser-first skill editor.
