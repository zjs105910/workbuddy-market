# Capture and indexing

Capture normalizes enabled sources into events. The [source inventory](../data-handling.md#sources) lists locations and consent settings. Definitions are in `packages/core/src/config/schema.ts`, and adapters are in `packages/sessions/src/observe/adapters/`.

## Consent and discovery

Before consent, setup reads at most one directory entry to learn whether a configured root has data. It keeps only a boolean and opens no source contents.

After consent, repository instruction import accepts the three supported root instruction files and direct skill documents. It rejects symlinks and enforces file and byte limits before it materializes content. Git remote discovery has separate consent. Without it, working directories stay isolated.

## Events and text references

`AgentEvent` records source, session and event identity, order, timestamp, working directory, kind, tool metadata, and an optional `TextRef`. See `packages/sessions/src/observe/types.ts`.

The event index holds no transcript text. A file reference selects a bounded byte range. A Cursor reference selects a text field in a content-addressed SQLite blob. `resolveRedacted` checks the reference and redacts the selected text before it becomes learning input.

Only user-authored text is learning evidence. Tool results, tool-returned file contents, thinking blocks, and data-access results get no eligible reference. Agent responses, plans, and questions appear only as labeled context beside a user correction.

## Incremental reads

JSONL cursors track source size, modification time, and the last complete byte offset. A read starts at that offset. Truncation, rewrites, and invalid boundaries cause a rescan. A partial trailing line waits for a later run.

Oversized records and databases are skipped with diagnostics. SQLite chat sources are rescanned when their database, write-ahead log, or metadata changes. The index also records observed source, session, and repository bindings. A schema rebuild keeps them, but deleting the database loses them.

## Adapter distinctions

- **Claude Code:** assistant blocks can share a message identity, tool results can arrive as user records, and injected metadata is not guidance. Subagent transcripts are discovered separately from parent files.
- **Codex:** message and event streams can describe the same turn, so adapters count one.
- **Pi:** version 3 JSONL keeps parent links. Each correction has its own ancestor context, without tools, thinking, injected messages, or summaries.
- **Cursor:** chat databases hold JSON messages and opaque blobs. Adapters read only supported records.
- **Antigravity:** generated logs give conversation records and cancellation signals. Capture queries no live daemon and writes no sidecars.

Interruption markers have no stable schema, so marker-health diagnostics report suspicious gaps.

## Learning triggers

When automatic learning is on, native integrations issue an opaque session token. When the agent marks a session useful, the end hook can schedule a bounded worker. A stop alone does not authorize learning. The worker selects unprocessed evidence for that session and records progress.

The Claude plugin transcript hook validates its path, checks consent and policy, and ingests that file through the shared cursor. It makes no rules itself. No always-on daemon is required.

## Verification

Adapter tests use synthetic secrets and cover appends, rewrites, incomplete records, duplicate provider views, and changed references.
