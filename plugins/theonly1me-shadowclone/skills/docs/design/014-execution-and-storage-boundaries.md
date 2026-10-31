# Execution and storage boundaries

This proposal identified the isolation work that [remediation completion](021-remediation-completion.md) completed.

## Problem

Provider flags alone could not guarantee that a process stayed within its intended filesystem and environment. Private derived state, repository identities, and evaluation artifacts also needed consistent handling.

## Decision

Separate learning, coding, and verification processes by purpose. Give each a controlled environment, bounded resources, and the smallest filesystem access it needs. Unsupported isolation must fail closed before execution.

Keep private state in user-owned storage with restrictive permissions. Resolve repository identities from complete remote namespaces, including meaningful ports. Use a digest to avoid collisions. Unrecognized remotes must not acquire the guidance of another repository.

Read source metadata and redacted text from the same bounded snapshot. A model request or publication decision cannot use a hash from one read and content from another.

Keep raw evaluation evidence private. Public reports contain reduced scores and limitations. They contain no prompts, identifying paths, or generated private code.

## Verification

Test the boundaries through real child processes with synthetic data: denied host reads, denied network access where required, termination, resource limits, and private file permissions. Platform support depends on those controls working. The completion record describes the implemented contracts and the remaining limits.
