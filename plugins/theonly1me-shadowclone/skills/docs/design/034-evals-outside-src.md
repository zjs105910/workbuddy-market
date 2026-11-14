# Evaluations outside src

## Problem

`src/eval` held 203 files of contributor-only benchmark code. `src/cli/index.ts` registered `shadowclone eval` through five wrappers in `src/cli`. The bundler followed those imports, so the shipped `dist/shadowclone.js` carried the evaluation protocols. The published 0.0.19 bundle is 4,683 KB and contains the `preference-respect` strings. The documentation already says packaged builds do not run the benchmark.

## Decision

Move `src/eval` to `evals/`, one to one, so `src/eval/fixed` becomes `evals/fixed`. Move the five wrappers and their three tests from `src/cli` to `evals/cli`. `evals/run.ts` is the new entry point, run with `bun run eval`. It dispatches in the order that the CLI used. `src/cli/index.ts` no longer has an `eval` command or an evaluation usage line.

Some code depends on where it sits, so the move is more than renames.

- Repo-root lookups through `import.meta.dir` lose one level, in `evals/fixed/identity.ts`, `evals/fixed/reusable/{execution,preparation,reuse}.ts`, `evals/native/study/phases.ts`, and `evals/work/prepare.ts`.
- `evals/fixed/reusable/learningSource.ts` lists the evaluator files under `evals/`. Its `src/**/*.ts` scan no longer has to skip the evaluation code.
- `package.json` gains `eval` and points `eval:work` at `evals/work/run.ts`. `knip.json` lists the new entries.

The sequence was:

1. `git mv`.
2. A script that rewrites relative imports (176 specifiers in 65 files).
3. The typechecker.
4. The path fixes above.
5. The command removal and the documentation.

## Consequences

- `shadowclone eval` no longer exists in the installed CLI. Run evaluations from a source checkout with `bun run eval`.
- Fingerprints that depend on the code change. Offline preparation on `main` and on this change differs in four fields: the product tree, the branch, `corpusFingerprint`, and `learningStateFingerprint`. Preparations and receipts made before this change do not match code after it. Published results in `evals.md` do not change.
- Branches that edit these files need a rebase. Git detects the renames.
- `evals/no-comments` was already outside `src`, and the change leaves it alone.

## Verification

- `bun run check` passes: typecheck, lint, and 1,096 tests, with 332 test files before and after.
- `bun run build` produces a 747 KB bundle, down from 4,683 KB, with no `preference-respect` strings.
- `bun run eval --protocol preference-respect-v3 --help` prints the evaluation help. `bun run cli eval` prints the usage and exits 1.
