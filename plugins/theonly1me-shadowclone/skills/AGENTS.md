# Working on Shadowclone

Shadowclone maintains portable coding-agent skills from consented sessions and memory. It delivers skills and small native instruction sections. Legacy profiles remain for migration.

Follow `CONTRIBUTING.md` when you edit code or prose. Read `.claude/skills/data-handling/SKILL.md` before you change capture, storage, model access, or user actions. Read a package `AGENTS.md` before you change that package.

## Layout

- `packages/*`: the `@shadowclone/<name>` packages, with dependencies in the [architecture](docs/architecture/README.md).
- `skills/`, `preferences/`, `plugins/`: bundled content that installers find at the root.
- `evals/`, `tooling/`: private workspaces for evaluations and repository checks.

## Package rules

- Import another package only by its name and its declared subpaths, such as `./testing` and `./browser`.
- `tooling/src/boundaries/packages.ts` holds the package graph, and the boundary check enforces it. Add a dependency edge only with a design record.
- If a change alters the purpose, exports, dependencies, or rules of a package, update its guide in the same commit and run `bun run guides`. Lint fails when a guide is missing or out of date.

## Work on the requested change

Inspect the worktree and keep unrelated edits. Before you implement, record the reasoning and sequence in `docs/`. If you extend a design, use its existing record. Keep types and names explicit. Use Bun and the existing module boundaries. Add a dependency only for a concrete reason.

Keep active skills delivery separate from legacy profile compatibility. Never inject an aggregated profile into an active skill environment.

## Checks

```bash
bun install
bun run check
bun test packages/skills
bun run cli --help
bun run build
bun run stage
```

`bun run check` runs typecheck, lint, knip, and tests. Run focused checks while you edit and the full gate before handoff. Report earlier failures separately. Tests use synthetic fixtures. An authenticated run or paid evaluation needs an explicitly authorized scope.

## Data boundaries

- Keep private repository material, transcripts, receipts, and identifying paths outside this public checkout, including ignored files. Use synthetic examples that you wrote yourself.
- Public evaluation material may name models and versions. It must not name evaluators, billing details, private installations, paths, or repositories. An evaluation of public code may name its public repositories.
- Each capture source needs its own consent flag, off by default. Document each new source in `docs/data-handling.md`.
- Resolve eligible learning text through `resolveRedacted`. Exclude tool results, tool-returned file contents, thinking blocks, and data-access results from learning.
- Keep repository and remote-owner scope. Global guidance needs explicit global evidence or a direct user decision.
- Keep manual edits and ownership checks when you write skills or native instructions. Keep every change reversible.

## Documentation

- Write all Markdown and all text that a person reads in ASD-STE100 Simplified Technical English at about 80% strictness, with the `write-plain-english` skill. `CHANGELOG.md`, which Release Please writes, is exempt.
- Update each page that your change affects (start at the [documentation index](docs/README.md)). Update the architecture diagram when the flow or a trust boundary changes.
- Write for the reader of the page. Remove session narration, expired instructions, and duplicate explanations. Label historical designs as history.
- Keep the README a short path to a working setup: a quick start with time estimates, plain results, and a privacy summary. Put detail in `docs/guides/`. User-facing commands use the installed `shadowclone` CLI. Bun commands belong in contributor instructions.

## Handoff and Git

Explain what changed, how you verified it, and the remaining limits. Commit, push, and open a draft pull request without a diff review. Before you push to a branch that has a pull request, run `gh pr view --json state`.

Commit messages and pull request titles use one lowercase conventional-commit subject, such as `fix: keep cursors after a failed index`, with no body and no co-author trailer. A squash merge uses the title as the subject on `main`, and Release Please creates releases only from conventional commits. Never force push or amend a pushed commit.

<shadowclone-guidance>
## Your agent build

Follow repository requirements. Repository build choices override personal global choices. Load each selected workflow skill at the moment listed for it. When a selected workflow skill conflicts with the user's own skills or learned baseline rules, follow the user's guidance.

- when a change adds a skip, block, fallback, default, or retry: choose-by-consequence
- when designing or reshaping a module or subsystem: design-deep-modules
- when behavior is wrong or slow and the cause is not known: diagnose-before-editing
- before a change that has many steps or open design choices: plan-with-review-page
- when a decision depends on facts outside the repository: research-primary-sources
- while a merge, rebase, or cherry-pick has conflicts: resolve-conflicts-by-intent
- when fixing a bug, a regression, or a confirmed review finding: scope-confirmed-changes
- when a pull request needs a review: shadowclone-review
- when taking a change or a pull request to ready for review: shadowclone-work
- when adding, changing, or proving a test: tests-that-catch-bugs
- when changing TypeScript types or input that enters typed code: typescript-type-safety
- before you say that work is done or ready for review: verify-and-review
- before you write any text that a person reads: write-plain-english
Follow the selected working preferences in the shadowclone-build-preferences skill when relevant.
</shadowclone-guidance>
