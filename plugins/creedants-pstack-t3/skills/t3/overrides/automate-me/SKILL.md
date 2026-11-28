---
name: automate-me
description: "Use for \"automate me\", \"create/update/refresh my -mode skill\", \"turn/capture my preferences or working style into a skill\", or wanting agents to follow how the user works. Drafts or revises a personal -mode skill via pstack-author-skill + unslop, installed for every T3 provider, optionally pulling fresh evidence from recent T3 threads."
disable-model-invocation: true
---

# Automate me

A guided flow for turning the user's working conventions into a skill agents will follow. The output is one `-mode` skill tailored to them (e.g. `jay-mode`, `priya-mode`).

This skill orchestrates three others: an inline mining pass (see step 1), the [`pstack-author-skill`](../pstack-author-skill/SKILL.md) skill (authoring), and the **unslop** skill (prose discipline). It sequences them. It doesn't replace them.

## Flow

[The runtime's Modes section](../pstack-runtime/SKILL.md#modes) sets the mode lines of every brief this skill writes and how its spawns run in light mode.

### 0. Check for an existing skill

Look recursively for `*-mode/SKILL.md` matching the user's handle in every place a T3 provider loads skills from (table in step 4), plus `~/.config/pstack-t3/personal/`. In the project, check `.claude/skills/**` and `.agents/skills/**`. Mode skills can live in a personal category directory (`<skills dir>/<handle>/`), not only at the top level. Resolve symlinks (`readlink -f`) so one skill linked into four provider dirs counts once, and edit its real file. If one exists, confirm intent with the host's question tool (unless they already said "update my skill" or similar):

- Update the existing skill (default for repeat runs)
- Start fresh (rare, ask why before doing it)

Update mode changes the rest of the flow:
- Step 1 mines only history since the skill was last edited (`git log -1 --format=%cI <path>`).
- Step 2 asks what's changed or missing, not what to capture from zero.
- Step 4 edits the existing file in place. Preserve sections the user hasn't contradicted. Revise ones with new evidence. Add new sections only for genuinely new rules.

### 1. Mine their history

Locate the current project's T3 threads before fanning out. List them with `t3_thread_list` (newest first, paged by `cursor`, `settled: true` for threads moved out of the active list) and keep the `threadId`s in the window. T3's thread tools stay inside the current project. Don't ask the user to attach threads from unrelated projects unless they offer. That reads private chats from unrelated work.

Survey recent agent conversations within that scope for recurring patterns. Run multiple parallel children with `delegate_task` (`mode: "async"`, `role: "research"`, a read-only brief) across slices of history (e.g. last 2-4 weeks, split into 3 slices so each has enough material). Each mining child's brief lists every `threadId` in its assignment, and the child reads each one. An assignment is never a sample or a pick of the relevant threads. It reads with `t3_thread_read` (`view: "messages"`, paged with `afterPosition`), looks for the signals below, and returns a short structured list of patterns it saw with `threadId` evidence pointers. Default signals worth hunting:

- Response preferences (length, tone, format, "dumb it down" corrections)
- Delegation habits (subagents, models, specialized workflows, parallelism)
- Verification posture (what "done" means, unit tests vs live repro, reviewers)
- Code and prose discipline (style, principles cited, lint/format tools)
- Process conventions (worktrees, commits, PRs, review/merge tooling)
- Meta preferences (fixing skills mid-task, proposing new ones)

Cross-check across slices before elevating a signal. Patterns seen in 2+ slices are high-confidence. Lone signals are weak and usually get dropped.

### 2. Ask the user directly

Mining misses intent that hasn't come up yet. Use the host's question tool with structured multi-choice when it has one, rather than asking the user to type from scratch. Without one, ask the same lettered options in a short reply.

Shape: one or two questions with 4-6 options each, multi-select for category questions. Start broad ("Which areas matter most?"), then follow up on selected areas with specific options. After the structured rounds, one free-form chat question catches anything the options missed.

Don't dump 20 questions.

### 3. Cluster findings

Group the combined signals into sections. Common ones (use only what applies):

- **Response style**: length, tone, format.
- **Autonomy**: how much to do without asking, MCP tool use.
- **Understand first**: which skills to reach for when scoping or investigating a change.
- **Subagents**: default, parallelism, model-to-task, specialized workflows.
- **Prose / code discipline**: principles, lint tools, style guides.
- **Review and verify**: repro posture, verification skills, live-testing tools.
- **Process**: git worktrees, commits, PRs, review/merge tooling.
- **Skills**: skill-authoring habits, fix-the-skill-first, proposing new skills.

The **poteto-mode** skill shows the shape. Read it for granularity. Don't copy its content. The user's rules are not the same as poteto-mode's.

### 4. Draft the skill

Use the `pstack-author-skill` skill to author the skill. T3 can run any provider, and each provider loads skills from its own directory. A mode skill only one provider can see stops applying the moment the user switches models. Write it once and install it everywhere.

| Provider | User skill directory | Project skill directory |
| --- | --- | --- |
| Claude Code | `~/.claude/skills/` | `.claude/skills/` |
| Codex | `~/.agents/skills/` | `.agents/skills/` |
| Grok | `~/.grok/skills/` | none assumed |
| Cursor | `~/.cursor/skills/` | `.agents/skills/` |

Placement:

- Path: preserve an existing mode skill's location and category. For a new personal mode, write the real files to `~/.config/pstack-t3/personal/<handle>-mode/SKILL.md` and symlink that directory into every user skill directory above:

  ```bash
  src="$HOME/.config/pstack-t3/personal/<handle>-mode"
  for dir in "$HOME/.claude/skills" "$HOME/.agents/skills" "$HOME/.grok/skills" "$HOME/.cursor/skills"; do
    mkdir -p "$dir" && ln -sfn "$src" "$dir/<handle>-mode"
  done
  ```

  The loop is idempotent. Skip a provider the user does not run, and say which.
- For a mode the team shares through the repo, write the real files to `.agents/skills/<handle>-mode/` (or `.agents/skills/<handle>/<handle>-mode/` when the repo has a personal category for that handle) and add a relative symlink at the matching `.claude/skills/` path, so Claude, Codex, and Cursor all load it.
- Handle: the user's first name or chosen identifier.
- Frontmatter `description`: trigger on their name + `/<handle>-mode` + "work in their style", not on generic keywords like "write code" or "review PR".
- Frontmatter formatting: follow `pstack-author-skill`'s frontmatter rules. `name` equals the directory name. Keep `description` as one YAML scalar. Quote it or use `description: >-` with indented continuation lines when punctuation or wrapping requires it.
- Frontmatter `disable-model-invocation: true` by default. Opt out only if the user explicitly wants their mode to apply on every turn. Providers that do not know the key ignore it, so the description must still trigger only on the user's name and `/<handle>-mode`.

### 5. Iterate on prose

Apply the **unslop** skill and `pstack-author-skill`'s writing rules to every line.

Show the draft to the user and take feedback. Expect multiple iterations. Cut ruthlessly. A mode skill is not a manual.

### 6. Land it

For a repo-shared mode, work in a worktree off main. Commit and open a PR, then call `link_pull_request` with its URL. Don't push to main directly.

For a personal mode, there is no PR. Prove the install instead: `readlink -f` every symlink from step 4 resolves to the one real directory, and the skill shows up in T3's `$` skill picker.

## Guardrails

- **Don't overfit to one conversation.** A preference stated once and contradicted another time is noise. Require multiple instances before codifying it.
- **Don't be clever.** Restating other skills' contents, inventing metaphors, or writing "poetic" prose for an agent reader is cost without benefit. Keep it operational.
- **Reference, don't inline.** Other skills the user relies on should appear as path references, not pasted excerpts. Same for any principle docs they maintain elsewhere.
- **Keep sections minimal.** Only add a section if the user has a specific, non-default rule there. "Communicate clearly" is not a section. "Short paragraphs. Tables when comparing options. Bullets only when items are genuinely parallel." is.
- **Name conventions generic.** Use "the user" or "the human" in imperatives, not the author's first name.
- **Don't force symmetry.** If a user has no process rules worth writing down, skip the Process section entirely.

## Evaluation

A `-mode` skill is subjective output. A `pstack-author-skill`-style test/iterate benchmark loop isn't useful here. Vibe-check with the user: does it read like them? Did it miss anything? Then ship.

Run a description-optimization loop only if the skill's trigger accuracy turns out to be a problem in practice.

## When not to use

- User wants a task-specific skill (not working conventions): `pstack-author-skill` alone, no mining required.
- User wants to capture one narrow workflow (e.g. "how I write commit messages"). That's a regular skill, not a mode skill.

