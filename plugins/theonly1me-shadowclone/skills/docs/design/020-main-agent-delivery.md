# Delivering guidance to the main agent

This replaced subagent-only delivery. [Live context hooks](017-self-improving-agent-environment.md) later replaced copied profile text. [Skills delivery](023-skills-as-delivery.md) changed the content that Shadowclone delivers.

## Problem

A profile helped only when the user delegated to Shadowclone. Normal work in the main coding agent did not receive the learned preferences.

## Decision

Install scoped guidance through the native instruction mechanism of each agent. Use managed sections with ownership fingerprints. Keep the surrounding user text. Update only the sections that Shadowclone still owns. Keep existing hooks when you add the session hooks that context delivery and learning need.

Resolve context for the actual repository at session start. Personal installation and repository installation are distinct choices. Repository files that people can share must not silently receive private preferences.

Uninstall removes owned sections and hooks and keeps user changes. A conflicting edit needs review. Shadowclone does not overwrite or delete it.

## Tradeoffs and verification

Native instruction discovery differs by provider, so installing a file does not prove that the agent read it. Verify paths, hook payloads, scope selection, repeated installation, and removal independently. Live delivery probes must use isolated synthetic instructions. They must tell complete delivery apart from a partial tool preview.
