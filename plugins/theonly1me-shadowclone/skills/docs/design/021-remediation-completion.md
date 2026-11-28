# Execution and storage remediation

This completes the boundaries that [execution and storage boundaries](014-execution-and-storage-boundaries.md) proposed. The privacy architecture page (`docs/architecture/05-privacy.md`) summarized current behavior. Its content now lives in [data handling](../data-handling.md).

## Process isolation

Learning runs with a controlled environment and no tool or ambient-context access. Coding agents work in disposable repositories under the permissions for that run. Local verification runs without provider credentials, home-directory access, or network access.

OS enforcement adds to provider settings. Unsupported platforms or unavailable isolation mechanisms fail closed. Synthetic child-process probes must show denied reads and network calls. Building the expected arguments is not enough.

Set bounds on source reads, subprocess output, execution time, and process cleanup. Cancellation must end the owned process group. It must also stop late results from returning a completed or failed run to an active state.

## Consistent source snapshots

Read the source bytes once under a size limit. Then derive local metadata, fingerprints, and redacted model input from that snapshot. This stops reconciliation or compilation from pairing metadata with text that changed between reads.

Resolve repository identity from the complete remote namespace, including meaningful ports. Keep host and owner boundaries distinct, and include a digest where normalization could collide. An unknown identity stays isolated. Repository preflight must reject unsafe Git entries or filesystem paths before extraction or execution.

## Private storage and reports

Store derived guidance, revisions, checkpoints, and raw evaluation receipts in user-owned private directories. Apply restrictive permissions. Keep the executable bits that authorized artifacts need. Do not make broad permission changes to unrelated files.

Raw receipts can contain repository code and personal guidance. Reduced reports exclude those contents and identifying paths. Redact model explanations and diagnostics before you display them. Publish a reduced metric only after you review its surrounding labels and context.

## Verification and limits

Use independently authored fixtures for scope collisions, changing source files, malformed profiles, unsafe archive entries, storage permissions, output caps, cancellation, and blocked host access. Run platform-specific enforcement tests on the platform that they claim to support.

These controls constrain the processes and storage of Shadowclone. They do not make authorized provider requests offline. They do not guarantee perfect secret detection. They do not make private code safe to publish. [Data handling](../data-handling.md) describes what each operation can expose.
