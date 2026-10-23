---
name: how
description: "Use for \"how does X work\", code walkthroughs before changing something, and placement / ownership / layering questions (\"where should this live\", \"which package owns this\", \"is this the right layer\"). Explains subsystem architecture, runtime flow, onboarding mental models. Use why for motivation."
disable-model-invocation: true
---

# How

Explore the codebase to answer "how does X work?" questions. Produce architectural explanations at the level of a senior engineer onboarding onto a subsystem, enough to build a working mental model, not so much that it reads like annotated source code.

Each spawn below names a role, resolved per [the runtime's Roles section](../pstack-runtime/SKILL.md#roles) with `python3 <pstack-runtime>/scripts/roles.py show --cwd "$PWD" --parent "<inheritedProviderInstanceId>/<inheritedModel>" --role "<role>"`. Set `target` to the role's seat, or omit `target` when the seat is `inherit`. If `delegate_task` rejects a target, apply the runtime's fallback and say which seat changed and why. Every spawn uses `mode: "async"`, a stable `clientRequestId` such as `how-<slug>-<angle>`, and a read-only brief. The prompt templates tell the child not to edit files, commit, or push. Retain every returned `taskId`.

[The runtime's Modes section](../pstack-runtime/SKILL.md#modes) sets the mode lines of every brief this skill writes and how its spawns run in light mode.

## Step 1. Assess Complexity

If the scope is ambiguous, state your interpretation and explore. The user can redirect.

- **Simple** (a single module, a small utility, a narrow question such as "how does function X work"): no explorers. One explainer explores and explains in a single pass. Go to Step 2b.
- **Complex** (a subsystem spanning multiple files or services, a cross-cutting feature, a full architectural overview): spawn parallel explorers first, then hand off to the explainer. Go to Step 2a.

When in doubt, take the simple path.

## Step 2a. Explore (complex questions only)

Decompose the question into 2 to 4 exploration angles, each a distinct slice of the subsystem. Spawn all explorers in a single message:

- `delegate_task` with `role`: `"research"`
- `target`: the `how explorer` role

Each explorer gets the prompt in `references/explorer-prompt.md` with its angle filled in. Then go to Step 3.

## Step 2b. Direct Explain (simple questions)

Spawn one child task that explores and explains in one pass:

- `delegate_task` with `role`: `"general"`
- `target`: the `how explainer` role

Build its prompt from `references/explainer-prompt.md` without the explorer-findings section. Go to Step 4.

## Step 3. Synthesize (complex questions only)

Once all explorers have returned (collect them per [the runtime's Delegation step 5](../pstack-runtime/SKILL.md#delegation)), spawn one child task to synthesize their findings into one explanation:

- `delegate_task` with `role`: `"general"`
- `target`: the `how explainer` role

Build its prompt from `references/explainer-prompt.md` with every explorer's findings filled in.

## Step 4. Present

Present the explainer's output to the user. Light edits for clarity or context from the conversation are fine. Do not substantially rewrite it.

## Output Format

The explanation uses the sections defined in `references/explainer-prompt.md`, dropping any that do not apply: Overview, Key Concepts, How It Works, Where Things Live, Gotchas.
