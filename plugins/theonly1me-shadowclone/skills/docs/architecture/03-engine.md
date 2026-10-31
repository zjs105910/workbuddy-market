# Agent execution

`packages/agents/src/engine/` is the model-process boundary for learning and evaluation. It invokes an installed, authenticated agent CLI. Shadowclone needs no model account or API key of its own.

## Provider selection

The registry in `packages/agents/src/provider/` records capabilities apart from installation and authentication. Selection checks the purpose, then picks an eligible installed engine. `shadowclone doctor` reports availability.

- `claude-code`: structured output, isolated no-tools execution, caller session IDs, dollar budgets, and granular tool policy.
- `codex` and `cursor-agent`: structured output (prompted for Cursor) and isolated no-tools execution. These adapters have no native dollar ceiling.
- `pi`: learning only, through an owned extension. It passes prepared model input and an empty tool set through the Pi registry, with exact model selection and no dollar ceiling.
- `antigravity`: no engine. Capture and native guidance do not depend on engine support.
- `anthropic-api`, `openai-compatible`: reserved identifiers, not implemented.

Observation support does not allow learning or evaluation. An unsupported security option fails before the process starts.

Learning selection follows explicit command options, the harness and model of a triggering session, saved preferences, then detection. An unavailable or blocked engine gets no silent fallback.

## Execution purposes

`EngineRunOptions` needs an explicit purpose. The types in `packages/agents/src/engine/types.ts` define the request and result.

- **Learning:** no provider tools or ambient instructions. Only the prepared model input is available.
- **Evaluation:** read or write access to an isolated snapshot, with live personal context blocked as the protocol requires.

Results include usage, model and session identity, structured output, errors, and observed actions. Callers handle unknown cost and unsupported controls explicitly.

## Learning limits

One `createLearningExecution` instance owns the whole model allowance of a learning invocation, including reconciliation, consolidation, and skill maintenance. Defaults are 20 attempted calls and five minutes. Claude also gets a cumulative $2 ceiling. Setup uses 12 calls, 90 seconds, and a supported $1 ceiling. These limits cover model work, not the local scan.

Dollar-limited calls run serially, and each gets the allowance that remains. Unknown spend stops further calls. Engines without dollar enforcement use call and time limits only. Attempts, failures, and timeouts use calls. A deadline aborts the provider request. Completed checkpoints can be reused without a model call.

## Isolation

Learning adapters disable tools, hooks, MCP access, ambient instructions, and native memory with provider-specific controls. An empty auto-approval list alone is not a no-tools boundary. Provider output is bounded.

The Pi extension bypasses the coding agent loop. It calls `modelRegistry.streamSimple` with only prepared messages and an empty tool set. A live session uses a private authenticated socket. A standalone request runs an extension command in the installed Pi CLI from an empty temporary directory. Pi evaluation stays disabled, because its tool loop lacks qualified enforcement of the execution restrictions. See [Pi setup](../guides/pi.md).

Evaluation uses purpose-specific filesystem and process restrictions. Verification is a separate no-network process without provider credentials. Unsupported isolation fails before the affected operation.

See [delegated work](README.md#delegated-work), [evaluations](../../evals/README.md), and [data handling](../data-handling.md#what-reaches-a-model) for caller contracts.
