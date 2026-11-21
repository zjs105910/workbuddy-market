# Correcting safety defects

This record covers five confirmed defects in repository scope, redaction, and execution.

## Decisions

| Defect                                                                                          | Correction                                                                                                           |
| ----------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| Repository policy used a checkout directory name, which could differ from the remote repository | Resolve policy against the canonical repository identity. Keep local isolation when no remote identity is available. |
| Redaction rules kept characters from the match that held the secret                             | Keep only prefixes that are explicitly public. Fixtures prove that no secret characters survive.                     |
| Provider availability probes could wait indefinitely                                            | Limit the probe time. End the processes that time out.                                                               |
| Learning could install an integration into an arbitrary working directory                       | Find and validate the intended repository before installation.                                                       |
| The dispatch clean-exit requirement was unreachable through configuration                       | Make the configured requirement decide whether Shadowclone accepts a dispatch.                                       |

## Verification

Each regression test must reach the original defect through the affected public path. Use synthetic remote identities and secrets. Test the process cleanup after a timed-out probe, the installation outside a valid repository, and both clean-exit policy settings.

These fixes added no capture source and gave no new action authority. Later, [execution and storage remediation](021-remediation-completion.md) tightened the boundaries around them.
