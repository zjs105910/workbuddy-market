# My coding agent forgets the plan after /clear: the file-based fix

`/clear` empties the context window. Everything the agent knew only from the conversation is gone: the goal, the current phase, the errors it already hit. The next thing you see is the agent asking you to restate the task, then re-reading the repo to rediscover work it already finished. The fix is not a bigger window. The fix is keeping the plan somewhere `/clear` cannot reach: the filesystem.

This page describes the pattern planning-with-files implements. Overview: [README](../README.md).

## Why does my agent lose the plan after /clear?

Because in-context state is volatile by design. In-context todo lists disappear on context reset, goals stated once get crowded out after 50+ tool calls, and failures that are not written down get repeated. `/clear`, crashes, and [compaction](claude-code-lost-context-after-compaction.md) all destroy the same thing: state that was never persisted.

## Context window = RAM, filesystem = disk

The core principle, from the context-engineering pattern described in the [Manus blog](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus):

```
Context Window = RAM (volatile, limited)
Filesystem = Disk (persistent, unlimited)

→ Anything important gets written to disk.
```

Applied concretely, exactly three files land in your project root:

```
your-project/
├── task_plan.md   ← phases + checkboxes; the resume point after /clear
├── findings.md    ← research notes and decisions, appended as you go
└── progress.md    ← session log and test results
```

Plain markdown, gitignored by default, no runtime state anywhere else. Parallel tasks get isolated directories under `.planning/YYYY-MM-DD-slug/` instead.

## The re-injection loop

Files on disk only help if the model actually reads them, so that step is mechanical rather than left to model discipline. A `UserPromptSubmit` hook re-injects the active plan from disk at the start of every turn, wrapped in `===BEGIN PLAN DATA===` and `===END PLAN DATA===` markers. Companion hooks remind the agent to update `progress.md` after writes and check phase completion before stopping. The Claude Code plugin runs 6 lifecycle hooks, while its activation-scoped standalone skill runs 5. Codex runs 7 and Pi runs 8.

The loop means the plan is in front of the model by construction, not by hoping the model remembers to re-read it.

## What recovery looks like after /clear

1. The lifecycle hook restores selected context from the project planning files. It does not inspect host agent session stores.
2. The agent reads the three files, runs `git diff --stat`, and resumes at the current phase.
3. If the user explicitly requests local-history inspection, `session-catchup.py --metadata` reads same-project records and emits aggregate counts only. `--replay` may emit bounded nonce-framed excerpts.

A resumed session can answer the reboot questions from the files alone: where am I (current phase in `task_plan.md`), what is the goal (goal statement in the plan), what have I learned (`findings.md`), what have I done (`progress.md`). In the project's internal recovery benchmark (v1, author-run), a fresh session with the files on disk resumed in 5.0 turns on average against 13.3 for a raw agent; method and limits in [docs/evals.md](evals.md). That benchmark measured the earlier default transcript-catchup behavior, so it is historical evidence rather than a current file-only benchmark.

## Does this work outside Claude Code?

Yes. The skill installs across 60+ agents via the Agent Skills standard; the `npx skills` installer alone targets 71. Lifecycle hooks run on Claude Code, Codex, Cursor, GitHub Copilot, Kiro, and other platforms listed in the [README platform table](../README.md#works-across-18-platforms), and since v3.7.0 the repo also ships the `.agents/skills/` standard layout in-tree, so tools that read that path (Zed, Amp, Warp, Devin, Antigravity, Gemini CLI, Cursor) discover the skill from a plain `git clone`.

For runs that go beyond a single session, see [long-running agent tasks](long-running-agent-tasks.md): autonomous mode, the completion gate, and the run ledger build on the same three files.

## Related pages

- [Claude Code lost context after compaction: how to recover and prevent it](claude-code-lost-context-after-compaction.md)
- [Long-running agent tasks: keeping a coding agent on track for hours](long-running-agent-tasks.md)

## Install

Claude Code, plugin route (ships the skill, hooks, and slash commands):

```
/plugin marketplace add OthmanAdi/planning-with-files
/plugin install planning-with-files@planning-with-files
```

Every other agent, one line via the Agent Skills standard:

```bash
npx skills add OthmanAdi/planning-with-files --skill planning-with-files -g
```

Full route matrix and verification: [README](../README.md) and [docs/installation.md](installation.md).
