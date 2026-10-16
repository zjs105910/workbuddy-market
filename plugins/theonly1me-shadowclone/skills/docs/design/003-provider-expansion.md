# Qualifying provider support

## Problem

A provider may expose readable sessions without supporting isolated model calls or controlled actions. A single "supported" label hides those differences.

## Decision

Track observation, distillation, dispatch, and native integration independently in the provider registry. Declare a capability only when its adapter implements the required controls and qualification has exercised them.

Learning requires authenticated execution with tools and ambient context disabled, bounded input and output, cancellation, and structured results. Dispatch additionally requires enforceable tool restrictions, repository isolation, and the action-policy controls used by the caller. Unsupported combinations fail before execution.

Keep provider-specific argument construction and output parsing behind `src/engine/`. Shared callers check declared capabilities. Tests must distinguish a provider's advertised feature from a control Shadowclone can enforce.

## Antigravity boundary

Session capture and native guidance do not qualify an inference engine. The available logging and cancellation surfaces did not establish an enforceable tool-free execution mode. Antigravity therefore remains a capture and native-integration provider until Shadowclone can demonstrate that boundary.

## Verification

Use synthetic fixtures for parsing, timeouts, cancellation, model selection, and argument construction. Before you widen support, run a live probe that verifies the installed provider's actual behavior. Record limitations in the [engine architecture](../architecture/03-engine.md), which describes current capabilities.

## Pi integration

Pi remains the user's coding harness. Shadowclone installs portable skills, small native routing sections, and an owned lifecycle extension. Pi owns provider configuration, credentials, model selection, tools, and interactive sessions. Shadowclone does not add an agent loop or a model account.

The integration reads Pi sessions only with a separate `pi` source consent, disabled by default. It keeps message ancestry and file cursors. It reads eligible user and assistant text through `resolveRedacted`. It excludes thinking, tools, system messages, injected messages, and generated summaries. Original sessions remain in Pi's storage.

The extension runs bounded model requests through Pi's provider-neutral model API, with an empty tool set. Session-triggered learning uses a private authenticated socket to the live extension. This keeps providers that only that session registered. Standalone maintenance runs the installed Pi CLI with a command extension in an empty temporary directory. Both paths normalize responses into the existing engine contract.

A session-triggered learning worker keeps the originating harness and model. The order of choice is explicit options, then the originating harness and model, then saved distillation preferences, then existing engine detection. Configuration stores harness and model references. It stores no endpoints or credentials.

The implementation sequence is:

1. Registry and configuration.
2. Owned guidance and extension delivery.
3. Capture and redaction.
4. Model execution and selection.
5. Onboarding and diagnostics.
6. Synthetic and installed-harness qualification.

Existing rules for publication ownership, policy, cancellation, output bounds, and call and time limits apply in every step. Dispatch and evaluation stay unavailable until Pi meets their enforceable isolation and action-policy contracts.

Shared skill ownership must survive a partial refresh. One harness can refresh the shared skill while another keeps an edited extension. Then their recorded skill fingerprints can differ. Removing the harness with the current fingerprint transfers that verified ownership to the surviving harnesses before its manifest entry disappears. The transfer applies only when the current file matches the departing owner's fingerprint. Manual edits in between stay protected. Uninstall finds the current manifest entry by installation id, so a batch removal uses the ownership that an earlier step transferred. A regression test covers the partial refresh, both uninstall steps with an earlier manifest snapshot, and the final shared-file cleanup.

Applying managed policy keeps the saved harness and model references while it narrows execution permission. If it dropped those references, background maintenance, diagnostics, migration, and browser generation would ignore the user's selection. A blocked selection stays explicit and fails at the execution boundary. It does not become an implicit fallback. Regression tests cover Pi and the existing learning harnesses.

Browser generation previews show the selected model and keep that selection for the reviewed request. Cached generation results use the harness, model, and prepared input as the key, so a model switch cannot reuse a response from a different model. The existing harness-default behavior still applies when the user selects no model.

### Qualification results

The installed-harness checks used Pi 1.0.0 and synthetic material. Pi's existing coding loop wrote a requested function through Ollama. Its command bridge completed a prepared, tool-free model call with an exact provider/model selection. A later Pi session loaded the published native routing and found the shared skill after publication. The publication used valid synthetic learning responses.

The complete Pi/Ollama learning cycle remains unqualified with the tested local models. `llama3.2:latest` produced invalid learning JSON or schema results, and Shadowclone rejected them. `deepseek-r1:8b` exceeded the bounded learning deadline, and Shadowclone cancelled it. These outcomes establish the rejection and cancellation behavior. They do not establish successful preference extraction with those models. Synthetic contracts cover successful learning publication, lifecycle deduplication, provider extensions, ancestry, redaction, and reversible installation. Dispatch and evaluation remain disabled.
