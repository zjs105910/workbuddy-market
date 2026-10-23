# Bounded learning execution

## Problem

A learning pass could launch many independent model calls without a shared limit. Provider defaults could also expose tools or ambient instructions unrelated to the selected evidence.

## Decision

Give each learning run one budget for invocations, elapsed time, and provider-supported cost. The default limit is 20 calls and five minutes, with a $2 ceiling where cost is enforceable. Attempted calls count even when they fail. Stop when any limit runs out.

Use an explicit run purpose so learning cannot inherit dispatch permissions. Learning has no tools, repository access, ambient instructions, hooks, MCP servers, or implicit memory. The prompt contains only bounded, redacted inputs that the caller selects.

Save completed work, so a later pass can reuse valid checkpoints. Tie reuse to the inputs and the learning contract. A checkpoint does not permit a run to exceed the limits of the new run. [Agent builds](024-agent-builds.md) later made shared dollar reservations serial. They also stopped further calls when the cost was unknown.

## Tradeoffs

Some providers cannot report or enforce a dollar limit. Report that limitation and keep the invocation and time limits. Provider cancellation and host-process termination need independent enforcement. A timeout wrapper alone does not stop a child process.

## Verification

Test shared accounting, failed calls, cancellation, stale checkpoints, and exhausted limits with synthetic providers. Inspect the actual provider arguments. Confirm that they turn off tools and ambient discovery. Setup uses a smaller budget, which [launch readiness](019-launch-readiness.md) describes.
