---
name: recall
description: "Reconstruct your recent working context from your own chat history, live state, and the shared record (user reports, prior fixes, incidents), then hand back a tight current-state brief. Use for 'recall my work on X', 'catch me up', 'what have I been working on', 'where did I leave off', before starting or resuming work."
disable-model-invocation: true
---

# Recall

**Before you start or resume work, you rebuild the user's recent working context and hand back a tight capsule of where things stand now and what to do next.**

Keep it tight and on-topic. Read only what the in-scope threads need, then stop.

Your context lives in two records. Your own chat history holds what you did and decided. The shared record holds everything that happened around the same code under other names: the symptoms users keep reporting, the fixes that shipped and got reverted, the errors still firing in prod. That second record is what the **why** skill searches, across source control, the issue tracker, chat and issue channels, long-form docs, and error tracking. A feature with a long bug tail keeps most of its story there, so don't reconstruct it from your threads alone.

Your chat history is the current T3 project's threads (the runtime's [History section](../pstack-runtime/SKILL.md#history)). `t3_thread_list` lists them newest first, with run status and paging by `cursor`. Add `includeSubagents: true` to include child task threads, and `settled: true` for threads moved out of the active list. `t3_thread_search` matches a topic, branch, or PR number against titles and content. It is bounded, not exhaustive, so pair it with a dated `t3_thread_list` sweep when the window matters. `t3_thread_read` reads one thread: `view: "messages"` for the conversation, `view: "activity"` for tool calls, paged with `afterPosition`. Every thread is cited by its `threadId`.

[The runtime's Modes section](../pstack-runtime/SKILL.md#modes) sets the mode lines of every brief this skill writes and how its spawns run in light mode.

1. Classify, then route. One specific prior chat to resume is the `session-pickup` playbook, not this. Turning habits into a durable skill is `automate-me`. A human-readable summary of your work is a different task. Recall loads working context across recent chats before you act. If the user already gave you a full state capsule (paths, branch, the change), use it and skip the mining.
2. Lock the scope before searching. Pin the window ("recent" is a real range, default the last 7 days), the topic if named, and the project (default the active one. T3's thread tools only return this project's threads, plus any thread the user attached as context. Never read another project's threads without being asked). State the scope back. Never quietly turn "all" into "recent N".
3. Fan out across your chat history. List the in-window threads yourself with `t3_thread_list`, then spawn parallel children with `delegate_task` (`mode: "async"`, `role: "research"`, a read-only brief) on a fast, cheap model the user's roles offer, each taking a slice of the `threadId` list. Tell every child to keep the list's newest-first order and never reorder by id, run `t3_thread_search` on the topic first and then read only the matching threads and only their relevant regions with `t3_thread_read`, and skip the current thread plus obvious noise (child task, eval, and test threads, unless the topic lives in a child's work). Each returns the same schema, one block per thread: topic, the user's goal, decisions, open threads, struggles and corrections, and artifacts (PRs, tickets, branches), each citing the `threadId`. For one or two threads, skip the fan-out and read directly. The raw threads stay in the children. The main thread gets only their findings.
4. Sweep the shared record whenever the topic names a feature, file, subsystem, area, or bug. This is the default, not a judgment call, and "my work on X" does not exempt it. Hand it to the **why** skill's source investigators, but steer their question from "why was this built this way" to "what's the current state, what's been tried and didn't hold, and what are users still reporting". Reuse its per-source playbooks, run the investigators in parallel with the chat-history mining, and inherit its posture: one investigator per source, null results are findings, skip an unavailable MCP and say so. Fold what comes back into the brief. Skip this step only for pure activity recall with no named target ("what did I do this week"), where your own history and live state are the entire answer.
5. Verify against live state. Take the PRs, branches, and tickets that the mining and the sweep surfaced and check them with `git` and `gh`. `list_thread_pull_requests` names the PRs linked to this thread, and `t3_worktree_list` shows the project's worktrees and their branches. When the answer hinges on what an agent actually did (the tools it ran, files it read, errors it hit), read the thread's `view: "activity"` in full, recovering truncated items with `itemId` and `textOffset`, not just a summary.
6. Write the brief to the contract below. Group by thread. Stay on the named topic.

## Output contract

Lead with the capsule, then the thread status, then the problems, then the next move. Deeper detail goes below or gets cut.

- **Capsule.** At most 5 bullets. What this work is and where it stands overall.
- **Threads.** One line each, prefixed with exactly one status tag: `[merged #N]`, `[open PR #N]`, `[in flight <branch>]`, `[verified, uncommitted]`, `[reverted #N]`, or `[planned, not started]`. A thread with no tag is not done yet, so tag it.
- **Problems.** At most 5, the recurring ones. Include the symptoms users keep reporting and any fix that shipped and was reverted, so the next attempt starts where the last one failed.
- **Next move.** The single most useful next action, concrete.

An adjacent feature or ticket stays out unless it blocks this one. When the capsule and thread lines outgrow a screen, cut detail before you cut threads. Write the brief through the **unslop** skill, cite chat findings by `threadId` and shared-record findings by their source (PR #, ticket ID, chat permalink, error-tracker issue), and sanitize private context before any public output.

**Reply:** the brief, to the contract above.
