# Pull request review evaluation

This evaluation compares reviewers on merged pull requests from one public repository. The headline is precision: how many findings are real or wrong.

The local evaluation runs Shadowclone and openqodex on one machine, with no GitHub use:

- **Branch:** each case is a local repository with no remote. One commit on `case` over `main` holds the head tree, with the upstream title and description as its message.
- **Upstream:** both reviewers review the real pull request in a clone of the source repository, read it through `gh`, and post nothing.

## Cases

1. `mine/index.ts` lists merged pull requests in a window. For each fix, it blames the removed or changed lines and the line next to each pure insertion. The last pull request to touch them is a candidate that introduced a defect.
2. `validate.ts` gives both diffs to two judges, Claude Opus 5.5 and GPT 6.1 Sol. A candidate stays only when both agree that the fix repairs a defect from the earlier pull request.
3. `sample.ts` takes every validated defect case and a seeded sample of clean pull requests.
4. `prepare` builds the local case repositories and writes `prepared.json`. `copy` pushes each case as `case-<id>/base` and `case-<id>/head` branches and opens a draft pull request with a sanitized description.

## Arms

All arms use `claude-opus-5-5` at the default effort of Claude Code, except Greptile with its own models.

- **shadowclone-branch** and **shadowclone-upstream** run `shadowclone review --base main` and `shadowclone review <number>`, with checks on.
- **openqodex-branch** and **openqodex-upstream** run `npx openqodex review --base main` and `npx openqodex review '#<number>'`, with the Claude reviewer, web tools, and `ANTHROPIC_MODEL=claude-opus-5-5`.

The cloud arms are **Shadowclone** (`@shadowclone review`, which runs the released CLI), **openqodex** (the same command and settings), and **Greptile** (`@greptileai`), each on the pull request.

Each arm counts what its users see: posted or written findings for Shadowclone, `findings` and `outside_change` for openqodex, and inline review comments for Greptile.

## Grading

Grading pools and shuffles the findings of all arms for each case and removes tool names and links. Both judges read the head code and label each finding `real`, `minor`, or `wrong`. On a defect case, they also mark the findings that identify the defect. A label counts when both agree. The owner decides each disagreement blind.

## Run it

```bash
bun evals/pr-review/mine/index.ts --repo vitejs/vite --clone <clone> --since 2026-03-01 --until 2026-10-08 --introduced-before 2026-09-08 --fix-within-days 60 --output <dir>
bun evals/pr-review/cli.ts validate --mined <dir> --clone <clone>
bun evals/pr-review/cli.ts sample --mined <dir> --clean 27 --seed 20261009
bun evals/pr-review/cli.ts prepare --mined <dir> --clone <clone> --cases-dir <cases>
bun evals/pr-review/cli.ts run --arm shadowclone-branch --mined <dir> --runs <runs> --clone <clone> --model claude-opus-5-5
bun evals/pr-review/cli.ts judge --cases prepared.json --mined <dir> --runs <runs> --clone <clone> --seed 20261009
```

For the cloud evaluation, use these instead of `prepare` and the local runs, and judge with `--cases copied.json`:

```bash
bun evals/pr-review/cli.ts copy --mined <dir> --clone <clone> --eval-repo <owner/name>
bun evals/pr-review/cli.ts run --arm <arm> --mined <dir> --runs <runs> --eval-repo <owner/name> --checkout <eval-clone> --model claude-opus-5-5
```
