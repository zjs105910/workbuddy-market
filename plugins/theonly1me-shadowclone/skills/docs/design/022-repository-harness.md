# Repository instructions and checks

## Problem

Personal guidance alone did not give a project a repeatable setup or a way to check the conventions that it declared. Copying all learned guidance into startup instructions also duplicated repository rules and exceeded useful context limits.

## Decision

Build repository instructions and workflow skills from detected project checks and explicitly selected guidance. Read manifests only with the relevant consent. Preview `AGENTS.md`, the Claude import, portable skills, and the check configuration before Shadowclone writes them.

Ask before including personal preferences in shared files. Keep repository requirements distinct from private personal guidance. Copy selected skill resources with ownership checks. Keep existing instruction text.

Make configured checks available through the CLI and the dispatch gate. A bounded Claude stop-hook loop can request corrections after a failed check. Where the rule allows it, support checks on only the changed files. Do not claim that prose alone enforces behavior.

Limit startup context to a deduplicated 4 KiB index. Do not copy imported native guidance back into the same prompt. [Skills delivery](023-skills-as-delivery.md) replaced the remaining compiled profile with baseline and skill routing.

## Persistence and verification

Repository check configuration is explicit state. [Agent builds](024-agent-builds.md) later fixed refresh, so replacing profile prose with routing could not erase configured checks.

Test detection, consent, preview, cancellation, ownership, shared and private output, check execution, and bounded repair. The current [evaluation](../../evals.md) measures preference delivery separately from repository harness effectiveness.
