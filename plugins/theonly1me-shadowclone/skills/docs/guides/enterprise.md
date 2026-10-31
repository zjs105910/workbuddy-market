# Enterprise controls

A personal agent environment can hold guidance from several employers, clients, and projects. Source consent, repository scope, and managed policy limit where that guidance applies.

## Scope

Learning records carry their origin and scope:

- **Project guidance** goes only to its registered repository, after Shadowclone verifies its identity.
- **Organization guidance** applies inside a matching normalized remote owner.
- **Global guidance** needs explicit global evidence or a direct instruction from you. Repetition across owners does not make guidance global.

Without `git-metadata` consent, each working directory stays isolated. Missing or unclear identity does not make guidance global. Learning requests keep project and owner evidence apart, and local prompt tokens hide persistent identities. [Data handling](../data-handling.md#scope-and-editing) has the registration rules. Remote ownership is a technical identity, not a legal organization boundary.

## Managed policy

An administrator can place a policy file that root owns at `/Library/Application Support/shadowclone/managed.json` on macOS or `/etc/shadowclone/managed.json` on Linux:

```json
{
  "enabled": true,
  "allowedSources": ["claude-code"],
  "allowedEngines": ["claude-code"],
  "distillation": "allowed",
  "originScope": "strict",
  "blockedOrigins": ["github.com/example-team/restricted-*"],
  "maxActionTier": "draft"
}
```

User settings can narrow these permissions and cannot widen them.

- `enabled: false` turns Shadowclone off.
- `local-only` prevents learning with a hosted model. Shadowclone has no local model runner.
- A `draft` action ceiling prevents remote publishing, even when repository policy allows it.

`shadowclone doctor` reports the effective managed policy. Ownership checks protect the policy file from replacement by ordinary user configuration. These controls govern this installation, not other programs under the same account.

## Deployment review

Review the enabled sources, global guidance, approved providers, access to local state, and retention together. Provider access does not authorize you to send every repository or transcript.

Shadowclone does not encrypt local files. Deleting them does not remove data that a provider or a backup keeps. The project claims neither anonymity nor regulatory compliance. Check the implementation and provider agreements against your requirements. Use [private security reporting](../../SECURITY.md) for failures.
