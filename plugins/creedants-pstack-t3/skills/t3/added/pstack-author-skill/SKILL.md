---
name: pstack-author-skill
description: "Author, update, or tune a skill so it works under every provider T3 runs (Claude Code, Codex, Grok, Cursor): frontmatter, placement, lean body, and a fresh-child test. Use for 'write a skill', 'new skill for X', 'update this skill', 'tune this skill's description', or when reflect or automate-me hands off a skill edit."
---

# Author a skill

A skill is a folder with a `SKILL.md`. An agent reads it cold, mid-task, with no memory of why it was written. Write for that reader.

## 1. Decide the home

T3 can run any provider, and each provider loads skills from its own directories. Pick where the real files live, then link them everywhere the skill must work.

| Provider | User skill directory | Project skill directory |
| --- | --- | --- |
| Claude Code | `~/.claude/skills/` | `.claude/skills/` |
| Codex | `~/.agents/skills/` | `.agents/skills/` |
| Grok | `~/.grok/skills/` | none assumed |
| Cursor | `~/.cursor/skills/` | `.agents/skills/` |

- A project skill: real files in `.agents/skills/<name>/`, plus a relative link `.claude/skills/<name>` pointing at `../../.agents/skills/<name>`. If the repo already keeps skills only under `.claude/skills/`, invert it.
- A personal skill: real files in `~/.config/pstack-t3/personal/<name>/`, linked with `ln -sfn` into each user directory above for the providers the user runs.
- A pstack-t3 skill: edit `t3/overrides/<skill>/` or `t3/added/<skill>/` in the pstack-t3 repo and run `python3 scripts/build.py`. Never edit its generated `skills/` tree.
- Before creating, search every directory above for an existing skill that covers the topic. Extend it instead of adding a sibling.

## 2. Write the frontmatter

```yaml
---
name: <name>
description: "<what it does>. Use for '<trigger phrase>', '<trigger phrase>', or <situation>."
---
```

- `name` equals the directory name. Lowercase letters, digits, and hyphens, at most 64 characters.
- `description` is one YAML scalar of at most 1024 characters. Quote it, or use `description: >-` with indented continuation lines, when it holds a colon, a `#`, or wraps.
- The description names what the skill does and when to use it. Front-load the trigger phrases a user actually types and the situations that should load it. Name a sibling skill when the two are easy to confuse ("Use how for runtime behavior").
- Only `name` and `description` are portable. Provider-specific keys such as `disable-model-invocation` or `allowed-tools` work in some providers and are ignored by others. Never rely on one for correctness. A skill that must not auto-trigger also needs a description narrow enough not to.

## 3. Write the body

- Keep `SKILL.md` lean: the steps an agent follows every time, in order, each naming a concrete tool, path, command, or check. Aim for under 150 lines.
- Push conditional detail into `references/<topic>.md` and link it from the step that needs it, with a relative path from the skill directory. Say when to read it.
- Put repeatable mechanical work in `scripts/`, executable, with its invocation shown in the body.
- Name tools by their unprefixed name (`delegate_task`, not a harness-prefixed form). For delegation, models, scheduling, and isolation, link [the pstack-t3 runtime](../pstack-runtime/SKILL.md) instead of restating it. A skill installed outside the pstack tree names the `pstack-runtime` skill instead of a relative path.
- Short declarative sentences. No hedging. Apply the **unslop** skill to every line.

## 4. Test it on a fresh child

[The runtime's Modes section](../pstack-runtime/SKILL.md#modes) sets the mode lines of every brief this skill writes and how its spawns run in light mode.

A skill nobody has run is a draft. Test it with a child that has never seen it.

1. Check the install. Every link resolves (`readlink -f`). The frontmatter parses. Every linked reference and script exists. The skill appears in T3's `$` skill picker. The picker does not list Muse's skills ([skill locations](../pstack-runtime/SKILL.md#skill-locations)).
2. Resolve `skill tests` with `python3 <pstack-runtime>/scripts/roles.py show --cwd "$PWD" --catalog <file> --parent "<inheritedProviderInstanceId>/<inheritedModel>" --role "skill tests"`. Take the catalog and both parent values from `orchestrator_capabilities`. Spawn a fresh child with `delegate_task` (`mode: "wait"`, `role: "test"`, `target` set to that seat). When the role entry includes `haikuBrief`, paste those paragraphs unchanged at the end of the brief. A test that writes or runs commands stays on the `show` seat, unless its child launches seats. Run that test through `roles.py show` with `--launches-seats` per [Claude Haiku 5.5](../pstack-runtime/SKILL.md#claude-haiku-55), because a plain `show` can return a cursor seat. `role: "test"` is the task kind. The pstack role is only the argument to `roles.py`. It never goes in `delegate_task`'s `role`. Omit `target` only when the seat is `inherit`, and say that this child is the author because no catalog seat was available. The brief is one realistic task the skill should handle, invoking it by name ("Use the `<name>` skill to ..."). Give it nothing else from this conversation. Use a read-only brief unless the skill's job is to write, and then point the child at a scratch worktree or directory.
3. Read what it did with `t3_thread_read` on the returned `childThreadId`, `view: "activity"`. Confirm it read the `SKILL.md`, followed the steps in order, used the named tools, and produced the expected artifact. Where it guessed, stalled, or skipped a step, the skill is unclear there.
4. Fix the skill and test again with a new fresh child. Never message the old child to retry. It already knows the answer.
5. For a skill that must work under several providers, run one test on a seat from a different provider (target from `orchestrator_capabilities`). That proves the link for that provider's directory too.

## 5. Tune the description

Run this when a skill exists but did not trigger, or after writing a new one whose triggers are uncertain.

1. Write three prompts that should load the skill and two that should not, without naming the skill.
2. Send each prompt to a fresh child with `delegate_task` (`mode: "wait"`, `role: "test"`, `target` from the `skill tests` seat, read-only brief, the prompt as the whole task). Resolve that seat with `show --catalog` the same way as section 4 step 2 when this session has not already. Paste `haikuBrief` when present. Omit `target` only when the seat is `inherit`.
3. Read each child's `view: "activity"` and record whether it opened the skill's `SKILL.md`.
4. Rewrite the description to front-load the missed trigger phrases and to exclude the false matches, then rerun the prompts that failed. Stop when all five behave.

## 6. Report

Name the skill path, every link created, the test child's `childThreadId`, and what the test changed in the skill.
