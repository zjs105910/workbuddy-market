# The wizard map, build names, and voice capture

## Problem

The browser wizard does not scale to a real library, and it is tedious to use.

- A hub click zooms to 1.25 and keeps that focus, so each later render snaps back (`src/web/client/tree.ts`). The map gets about 646 px of width, and skill targets are 24 px. `d3-zoom` cancels a click after a small mouse movement.
- A large library starts collapsed. The grouping builds hubs from words in skill names and descriptions (`src/builds/constellation.ts`). A filler word can become a hub, and a large group splits into numbered hubs such as "And 1".
- The build title is always `The <hub> Pathfinder` (`src/builds/constellationIdentity.ts`), so a few names repeat.
- The starfield places 54 stars with fixed math (`src/web/client/starfield.ts`). Each load draws the same diagonal lines, and 7 fixed animation phases repeat.
- Nothing captures the user's writing voice. Skills that write for the user read `~/.agents/voice.md` (design record 032), but the wizard cannot help the user build or review that file.

The owner has about 70 local skills. The wizard must show all of them, not only the 13 bundled ones.

## Decision

### Fast model tier

`src/engine/fastTier.ts` maps each engine to a cheap model and a low effort for short generations.

| Engine      | Model                                             | Effort        |
| ----------- | ------------------------------------------------- | ------------- |
| Claude Code | `haiku`                                           | low           |
| Codex       | `gpt-6-luna`, a model preset in codex-cli 0.159.0 | low           |
| Cursor      | its default model                                 | not supported |
| Pi          | the saved model                                   | not supported |

`src/web/generationEngine.ts` takes a tier and stops replacing the model for fast calls. A fast call gets 1 call and a 30-second deadline. Where the provider supports a dollar cap, the cap is $0.05. If the provider rejects the model, the error shows on the character sheet.

On Claude Code, `--effort low` did not stop Haiku 4.5 from thinking. A three-skill name took 54 seconds and $0.043. The 30-second deadline usually stopped it first. The fast tier now also sets `MAX_THINKING_TOKENS=0` through the `env` key of the `--settings` JSON. It also replaces the default system prompt with one short sentence through `--system-prompt`. The call has no tools, so the default coding-agent prompt only added cost. Measured on the same name: with thinking off, the call took 5.8 seconds and $0.012. With the short system prompt, it took 5.8 seconds and $0.0035. Saved-tier calls do the learning. They keep thinking and the default prompt.

### Grouping

Skills group first by source: bundled skills, working preferences, custom skills, the user's skills, and each plugin. Inside a source, skills group by their `shadowclone-category` metadata. A skill without that metadata gets a category from a fixed keyword list, or goes to "More skills". A filler word is never a hub. A large group wraps in its row instead of splitting into numbered hubs.

### Horizontal star map

- The Shadowclone root sits at the left. Each hub has its own row, and its skills form a wrapping constellation to the right.
- All hubs stay expanded. The page scrolls vertically. There is no pan, no zoom, and no Fit or Reset button.
- The map uses the full width, and the character sheet stays visible on the right.
- Each skill is a button with a target of at least 44 px and a label of 13 to 14 px.
- One click equips or unequips a skill and shows its details. The map highlights the selected skill.
- A render updates classes in place, so keyboard focus survives.
- Search highlights matches and does not move the view.
- Below 720 px, the list view stays.
- `d3-zoom` goes away, with any other d3 package that the new layout does not need.

### Starfield

A pure generator places stars with a minimum distance between them, from a new random seed on each load. Each star has its own size, brightness, twinkle period, delay, and drift. The generator sets them as CSS custom properties. A rare shooting star crosses at random intervals. The star count scales with the area, and a resize keeps the existing stars. With `prefers-reduced-motion`, nothing moves. The field pauses while the tab is not visible.

### Build name

The default name is "An open canvas". Five seconds after the last equip change, the wizard asks the fast tier for a name, and the character sheet shows a loading state. A saved build that opens without a change shows a **Name my build** button, so opening the editor still makes no model request. The prompt asks for these parts:

- A class title of 2 to 4 words, grounded in the equipped skills.
- A profile of 2 sentences in the second person.
- 3 abilities, each tied to a named skill.
- 1 tradeoff.

The prompt never invents skills, and it uses no dashes. The request sends each preference on its own. The prompt names dimensions to vary, bans default titles such as "Pathfinder", and adds a random seed word, so names do not repeat. The wizard caches each result by selection. A failure shows on the sheet with a Retry button. The request sends only redacted skill titles and one-line summaries. The sheet names the engine and the model, and it has an off switch.

### Voice capture

- Consent: a new capture source, `github-writing`, off by default (`src/config/schema.ts`, `src/config/managed.ts`, `docs/data-handling.md`). The dialog turns it on or off, and turning it off discards collected writing.
- Collection: `src/voice/` reads the user's pull request titles and bodies, review comments, and commit messages through `runHostCommand`, with timeouts and bounded output. It skips text that an agent wrote: attribution lines, branches that start with `codex/`, `claude/`, or `cursor/`, and bot authors. It redacts with `redactSecrets` and caps the payload. With consent off, it makes no `gh` call.
- Profile: the user's saved model returns a voice profile with traits, and do and do not lists. It also returns 3 invented samples on fictional topics: a pull request body, a review comment, and a commit message. A rewrite of the samples after an edit uses the fast tier.
- Review: the **My voice** dialog shows the traits and the samples, and never the source text. A check rejects any sample that copies 8 or more consecutive words from a source. The user accepts the voice, edits a trait and rewrites the samples, or discards the result.
- Save: accepting writes `~/.agents/voice.md`. If that file exists or is a link, the wizard does not write it and names it instead.

### Sequence

Each step is one pull request, in this order:

1. This record.
2. The fast tier.
3. Grouping.
4. The horizontal map.
5. The starfield.
6. The build name.
7. Voice consent.
8. Voice capture.
9. The voice review panel.

A final pass checks the real wizard.

## Consequences

The wizard makes more model calls. It makes one fast call for each settled selection, and one call with the saved model for each voice capture. Each call has a bound and shows on the sheet, and the build name has an off switch.

Voice capture reads the user's GitHub writing through their own `gh` login. The consent flag, the filters for agent text, redaction, and the review of invented samples limit what reaches the model and what the user sees. Text that an agent wrote under the user's name can still pass the filters, so the user can discard the result.

Cheap model ids change over time. Each tier entry names its source, and a rejected model shows its error.

## Verification

- Layout tests run synthetic libraries of 20, 70, and 500 skills with plugin sources. No nodes or labels overlap, no hub uses a filler word, and scrolling reaches every node.
- Unit tests for the starfield: the generator keeps its minimum spacing and its bounds, differs by seed, and stops movement under reduced motion.
- Unit tests for the fast tier: Claude Code gets `--model haiku --effort low`, and Codex gets `gpt-6-luna` with low effort.
- Unit tests for naming: the 5-second debounce and the cache work, and a failure shows on the sheet.
- Unit tests for voice: with consent off, collection makes no `gh` call. The filter removes agent text, and redaction removes synthetic secrets. A sample that copies 8 words fails. The wizard does not write a linked `voice.md`.
- The real wizard in a throwaway home with about 70 skills: headless Chrome screenshots at 1440, 1920, and 390 px. One click equips a skill, nothing zooms, and two reloads show different star layouts. The name appears after the loading state, and the Voice panel shows only invented samples.

## Shared files through links

Many users keep one copy of their instructions and skills in `~/.agents` and link each agent to it. For example, `~/.codex/AGENTS.md` links to `~/.agents/AGENTS.md`, `~/.claude/CLAUDE.md` imports that file with `@`, and `~/.claude/skills/<name>` links to `~/.agents/skills/<name>`. The wizard preview stopped at the first link, so such a user could not review or apply any build.

Decisions:

- Skill copies: a destination folder can link to the skill's own source or to another destination of the same skill. Then the agent already reads that file. The wizard does not write or track it. The wizard skips a link to anything else, and the review names the link and its target.
- Instruction files: a global instruction file can link to a regular file inside the home folder. Then Shadowclone keeps the link and writes its block into that real file. The review shows the real path, and undo restores it. Shadowclone skips a link to anything else, as before.
- One block per agent: `~/.claude/CLAUDE.md` can import, with `@`, the file that the instruction file of another agent resolves to. Then Claude Code gets no block of its own. It reads the shared block through the import.
- `integrationFilePath` resolves the link, so install, sync, the wizard, and removal agree on one path.

Tests use the same layout in a throwaway home. They run the preview, the apply, and the undo. Afterwards, each link is the same.

## Category selection and collapsed groups

Equipping a large library one skill at a time is slow, and a fully expanded map is long.

- One click on a category equips every skill in it that the user can equip. If all of them are already equipped, the click unequips them. The click leaves plugin-managed and locked skills alone. When two skills in the category share an axis, it equips only the first.
- A chevron beside each category and source collapses or expands that group. A collapsed group shows how many skills it hides. An expanded group shows a left chevron, because groups extend to the right and fold back toward the left. A collapsed group shows a right chevron. Groups start expanded. The browser keeps the collapsed set in `localStorage` as a convenience, and the map works without it.
