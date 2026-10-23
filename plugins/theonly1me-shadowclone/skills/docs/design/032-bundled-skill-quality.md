# Bundled skills that earn trust on every host

## Problem

Agents need guardrails that hold on every host, not notes in one agent's private memory. The bundled skills do not provide them yet.

A recent fix shows the gap. `shadowclone init` met a symbolic link at `~/.codex/AGENTS.md`. Other agents share that file. The first fix skipped that agent by default. It printed the skip in the middle of the output and still counted the agent as installed. A second change had to make the skip visible. No bundled skill asked the agent to compare block, skip, and ask by their consequence. No bundled skill asked the agent to read the real output before it called the work done.

The 11 bundled skills have these weaknesses:

- Each has 33 to 44 lines and no worked example.
- Descriptions use abstract nouns ("ready for handoff", "proportional coverage") instead of words a user says. Routing reads only the description.
- No skill makes the agent run the user's command and check the real output: counts, final lines, and exit code.
- Several rules accept low-value work. Rerunning unit tests satisfies verification, and a helper test satisfies regression proof while the CLI symptom stays untested.
- `prove-regression-tests`, `testing-first`, and `testing-risk-based` overlap. The last two are exclusive choices on one axis.

The product also blocks better skills:

- Publication rejects a bundled skill that references `scripts/`, `references/`, or `assets/` (`src/builds/publication.ts`).
- The catalog republishes the installed copy of an equipped skill (`src/builds/catalog.ts`), so a rewritten bundled skill never reaches existing installs.
- The code finds the package root by checking for `skills/testing-first/SKILL.md` (`src/skills/library.ts`), so retiring that skill breaks every command.
- Routing lists one full description for each skill. The budget is 4,096 bytes, and the bundled set already uses about 3.2 KiB.
- A Codex repository install writes `AGENTS.override.md`. Codex reads at most one instruction file per folder, so this can hide a team's `AGENTS.md`.

## Decision

### One quality bar

A lint in `src/skills/quality.ts` runs with `bun run lint` and checks every bundled skill:

- Frontmatter has only `name`, `description`, and `metadata`, the fields that every host and the Agent Skills format accept.
- The description has 250 to 900 characters. It starts with "Use when" or "Use before". It quotes at least two phrases that a user says. It states the outcome. It ends with "Not for ... (use `<skill>`)", which names another bundled skill.
- `shadowclone-applies-when` is a moment phrase of 90 characters or fewer that starts with before, when, after, or while.
- The body has at most 150 lines, so the whole skill survives context compaction. Its sections, in order:
  1. Use when.
  2. Gates: 3 to 6 numbered rules, each with a yes-or-no outcome, inside the first 40 lines.
  3. Process.
  4. Example: Situation, Easy route, Hidden cost, Best route, and Evidence.
  5. Guardrails.
  6. Completion: at most 6 items. Each item is a command, an exit code, an output line, or a `file:line`.
- The text has no tool names that only one host has, and no em or en dash. It passes the plain-English checker and the privacy check.
- No sentence appears in more than two skills, except the shared voice block.
- Every referenced file exists one folder down. Every script is a dependency-free Node ESM file with its own test.

A temporary list names the skills that are not yet rewritten. The rules come first. The list empties as someone rewrites each skill.

### Catalog

| Skill                                                                                                                                 | Change                                                                                                                                                                                                                                                                                                                                                           |
| ------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tests-that-catch-bugs`                                                                                                               | New. Replaces `prove-regression-tests`, `testing-first`, and `testing-risk-based`. Test-first becomes an ordering option inside it, and the `testing-approach` axis goes away.                                                                                                                                                                                   |
| `choose-by-consequence`                                                                                                               | New. Compares a shortcut with the alternatives by its consequence for the user.                                                                                                                                                                                                                                                                                  |
| `verify-and-review`                                                                                                                   | Rewritten around the real outcome on the surface the user uses.                                                                                                                                                                                                                                                                                                  |
| `write-plain-english`                                                                                                                 | New. Simplified Technical English rules based on ASD-STE100, the dash rule, a checker script, and the voice block.                                                                                                                                                                                                                                               |
| `plan-with-review-page`                                                                                                               | New. Read-only planning, one round of decisions with recommendations, and a self-contained HTML review page.                                                                                                                                                                                                                                                     |
| `verify-review-findings`                                                                                                              | New. Verifies each review finding at the pull request head before any change.                                                                                                                                                                                                                                                                                    |
| `scope-confirmed-changes`                                                                                                             | Rewritten. It reproduces the issue before any fix, with a test, a real command, or the real interface. After the fix, the same reproduction must pass. If reproduction is impossible, reasoning from data and code is a labelled last resort. It keeps the change to confirmed, reachable behavior. It never turns a passing check red. It adds the voice block. |
| `diagnose-before-editing`, `design-deep-modules`, `research-primary-sources`, `resolve-conflicts-by-intent`, `typescript-type-safety` | Raised to the bar. Type safety prefers type guards and schemas over assertions.                                                                                                                                                                                                                                                                                  |
| `shadowclone-work`                                                                                                                    | Description order and voice block only. Its measured text stays, so the lint does not require Gates, an Example, a Completion list, or the plain-English check in its body. Its description still passes the checker.                                                                                                                                            |

The new names differ from common personal skill names, so a user's own `planning` or `scoped-fix` skill never blocks publication.

### Decision policy

`choose-by-consequence` carries one policy. A risky behavior choice is any block, skip, warning, retry, default, or fallback. It is risky when it touches user-owned or shared files, data, security, or public behavior such as CLI output and exit codes.

- While planning, the agent raises each risky choice as an open decision with options, with the option that fails loudly first.
- While executing, the agent acts without asking and picks the option that fails loudly. A skip counts as loud only when the summary counts it, the final output names it, and the exit status shows it.
- The agent never writes through a file it does not own, such as the target of a symbolic link.
- The handoff lists each choice with the real output line that shows it.

The routing header repeats one sentence of this policy for every host: show each skipped or degraded step in the final output and the handoff.

### Voice

Skills that write pull requests, commit messages, comments, or documents for the user share one voice block. The agent reads `~/.agents/voice.md` before it writes. If the file is missing, the agent builds it once. It uses the user's own merged pull requests, review comments, and commit messages. It keeps only text that the user wrote. It states the sources in its handoff. The agent never overwrites an existing or linked `voice.md`. Every host can read this path. Shadowclone writes only under `~/.agents/skills/<name>/`.

### Delivery

- Bundled skills publish their supporting files, and retirement removes them.
- `shadowclone sync` replaces an installed copy only when its text matches a version that Shadowclone shipped. It prints one line per updated skill. `src/skills/bundledVersions.json` records the fingerprint of every shipped version of each bundled skill file. A copy with any other text stays unchanged. Sync lists it for review. This includes an edit that a wizard apply copied to every location, because the apply records the edited text as the installed text. Only the `sync` command makes these updates. So background learning never changes a bundled skill without an output line.
- `src/builds/retired.ts` maps the three retired testing ids to `tests-that-catch-bugs`. A mapping applies only after the old id leaves the bundled library and its replacement is in it. Then sync selects the new skill wherever a build selected a retired one. It removes the retired copies and choice keys. It prints one line per build. A retired skill with an edited copy or a build editor change stays selected, and sync names it. If sync cannot install the replacement, it names the build and the reason. It leaves the build unchanged and exits with status 1. Users who chose `testing-first` also see a `shadowclone remember` hint. Nothing creates a rule for them.
- A build no longer fails to apply because it stores a deselected id that left the library. Only selected ids must exist.
- The package-root check reads the package name and stops depending on any one skill.
- Routing lines become `- <moment>: <skill>`. Shadowclone builds them from `shadowclone-applies-when`. With all 13 skills, routing uses about 1.6 KiB. Each host still lists the full descriptions through its own skill catalog. Before this change, a build with every bundled skill and preference used 4091 of the 4096 routing bytes. The routing budget test now requires such a build to leave 1 KiB for the user's own rules and skills.
- Routing lists an equipped skill without `shadowclone-applies-when` by name in one line. Examples are a user's own skill or a wizard custom skill. The line is `- when the task matches the skill's own description: <skill>, <skill>`. These skills used to route by their full description. Typical personal skills use 400 to 750 bytes each. Three or four of them next to the bundled set exceeded the budget, and the wizard blocked the build. Each name costs about 15 bytes, and the host lists the full description from its own skill folder. The skills of a private build stay outside every host's skill folders, so a description line did not make them loadable either. The 4 KiB limit stays. A larger limit only delays the same overflow while each session loads the duplicated descriptions.
- A delivery-matrix test installs every integration in a synthetic home. It checks that each host's skill folders hold byte-identical skills and that every host receives the same routing text. Known gaps are rows in the table of the test, so closing a gap changes a reviewed row.
- A Codex repository install stops before it writes an `AGENTS.override.md` next to a team `AGENTS.md`, and names both files. It also reports an override that Shadowclone created before the team file existed. An override that the user made stays the user's choice. Other agents in the same command still install, and the command exits with status 1.

### Checks that replace rules

- The skill lint.
- `scripts/skillVersions.ts` fails when a file in `skills/` has no recorded fingerprint. `--record` adds the current fingerprints and keeps every earlier one.
- `scripts/privacy.ts` scans `skills/`, `preferences/`, and `plugins/shadowclone/skills/`. It flags email addresses, home paths that are not synthetic, `owner/repo#N` references, and URLs not on an allowlist. It also flags gendered pronouns where a skill should say "the user". It flags private terms too. The script stores them as SHA-256 hashes, so the plain names never enter the repository.
- `scripts/conventions.ts` rejects the en dash as well as the em dash, and also checks `.mjs` and `.html` files.
- `skills/write-plain-english/scripts/check-ste.mjs` reports dashes and sentences over 25 words as errors. It reports passive voice, phrasal verbs, and vague words as warnings. It skips code and quoted examples. The skill lint runs it on each finished skill and fails on its errors.
- A skill with `shadowclone-voice: "true"` metadata must contain the voice block from `src/skills/voiceBlock.ts`. The repeated sentence check skips that block.
- The review page validator, the routing budget test, the migration tests, the `voice.md` write guard, and the delivery matrix.

### Sequence

Each step is one pull request:

1. This record.
2. The dash rule.
3. The skill lint.
4. The privacy check.
5. The delivery matrix.
6. Supporting files.
7. Sync updates.
8. The migration.
9. Routing.
10. The six new or rewritten skills.
11. The remaining skills.
12. The Codex override block.

## Consequences

No evaluation gates these skills. The owner tests them in use. Each skill lands in its own pull request, so one that triggers or behaves worse reverts alone. The routing header has its own pull request for the same reason. Earlier measurements showed that routing text moved preference adherence by -7.9 to +2.3 points.

Sync now changes skill files on users' machines. It changes only copies whose fingerprint still matches the published text, and it reports each change.

The ideas behind several gates come from the public, MIT-licensed skill collections `mattpocock/skills`, `poteto/noodle`, and the pstack plugin in `cursor/plugins`. The text in this repository is original.

Three delivery gaps stay open for a later change:

- Private builds reach no host.
- The global skill folder of the Antigravity CLI receives nothing.
- Cursor reads both `~/.agents/skills` and `~/.claude/skills`, so each global skill reaches it twice.

The documentation of Cursor does not say how it treats two skills with the same name.

## Verification

- `bun run check` passes, including the skill lint, the privacy check, and the conventions check.
- `bun test src/integrations/deliveryMatrix.test.ts` shows every host receiving the same skills and routing text.
- The plain-English checker reports no errors on every bundled skill, under both `node` and `bun`, except in the measured body of `shadowclone-work`.
- Use a synthetic home with an old build that selected `testing-first`. Then `shadowclone sync` prints one line per update and swap, lists edited copies, reports true counts, and exits 0.
