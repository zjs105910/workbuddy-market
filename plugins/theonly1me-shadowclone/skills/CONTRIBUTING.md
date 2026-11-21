# Contributing

## Development setup

Install [Bun](https://bun.sh) 1.4.2, as `package.json` declares. Run `bun install` and `bun run check`.

Use `bun run cli` to run Shadowclone from the checkout. A command that calls a model needs an installed and authenticated `claude`, `codex`, or `cursor-agent` CLI. Tests use synthetic fixtures and need no account. On Linux, install `bubblewrap` and `socat`, which the Claude sandbox checks need. `bun run cli init` changes your local setup, so use isolated test paths for installation, learning, or removal tests.

## Repository layout

The repository is a Bun workspace. Each package in `packages/` is `@shadowclone/<name>` and has its own `AGENTS.md`. `evals/` and `tooling/` are private workspaces. The [architecture](docs/architecture/README.md) shows the package graph, and `bun run lint` checks every import against it.

## Making a change

Describe the problem and the approach in `docs/` before you implement. For a new product or architecture decision, use the [design template](docs/design/template.md) and add the record to the [index](docs/design/README.md).

Keep changes focused and add tests for behavior that can regress. Before you submit, run `bun run check`: typecheck, lint, the knip unused-file check, and tests. Turborepo caches `typecheck` and `test`. CI also runs the tests on Linux and macOS. The [plugin security scan](.github/workflows/plugin-security-scan.yml) needs a score of at least 80 and no high-severity finding.

## Add a package

1. Create `packages/<name>/package.json`. Set `name` to `@shadowclone/<name>`, `private` to `true`, and `type` to `module`. Set no version.
2. Add `exports` with `"."` for `./src/index.ts`. Add `./testing` or `./browser` only when other packages need them.
3. Add the scripts `typecheck` (`tsc --noEmit`) and `test` (`bun test`). Add a `tsconfig.json` that extends `../../tsconfig.base.json` and includes `["src"]`.
4. In `tooling/src/boundaries/packages.ts`, add the name to `packageNames` and a row to `allowedDependencies`. Record each new dependency edge in a design record.
5. Add an `AGENTS.md` in the shape of another package guide, a `CLAUDE.md` that contains only `@AGENTS.md`, and a row in the table in `docs/architecture/README.md`.
6. Run `bun install`, `bun run guides`, and `bun run check`.

## Code conventions

- Use complete names, and an options object for functions with two or more arguments.
- Keep TypeScript files at 300 lines or fewer, including tests.
- Avoid `any`, non-null assertions, type assertions other than `as const`, and unhandled or voided promises.
- Write code without comments. Express intent in names, types, functions, and tests. Leave unrelated existing comments alone.
- Fix lint findings. Do not suppress rules.
- Format changed files with `bun run format <files>`. Check them with `bun run format:check <files>`.
- Do not use em dashes or en dashes.
- Keep each bundled skill in `skills/` at the quality bar of [design record 032](docs/design/032-bundled-skill-quality.md). `bun run lint` checks it with `tooling/src/skills.ts`, and runs `skills/write-plain-english/scripts/check-ste.mjs` on it.
- A skill that writes for the user sets `shadowclone-voice: "true"` and contains the voice block from `packages/skills/src/skills/voiceBlock.ts`.
- After you change a file in `skills/`, run `bun run tooling/src/skillVersions.ts --record`. Lint fails until you do. `shadowclone sync` replaces an installed copy only when its text matches a recorded version.

## Documentation

Follow the documentation rules in [AGENTS.md](AGENTS.md). Put historical decisions in design records. Keep current guides true.

`bun run lint` reports plain English errors, broken relative links, and a package `AGENTS.md` that is missing or out of date. `bun run guides` rewrites the facts block of every guide.

## Pull requests

Use the [PR template](.github/pull_request_template.md). Keep the body under 250 words, with one sentence for each of at most seven change bullets and at most three sentences on why. Include the verification and any material limit. Remove unused sections. [AGENTS.md](AGENTS.md#handoff-and-git) sets the format of commit messages and titles.

## Changes that involve user data

Read [data handling](docs/data-handling.md) and the [contributor data rules](.claude/skills/data-handling/SKILL.md) before you change capture, storage, model requests, or delegated actions. Tests must use the real input path with synthetic sensitive values.

Shipped guidance in `skills/`, `preferences/`, and `plugins/shadowclone/skills/` must hold no private material. `tooling/src/privacy.ts` flags email addresses, machine paths, repository item references, unlisted URLs, gendered pronouns, and private terms. To add a private term, run `bun run tooling/src/privacy.ts --hash "<term>"` and add the printed hash to `tooling/src/privacyTerms.json`.

Report exposures as [SECURITY.md](SECURITY.md) describes.

## Releasing

Release Please maintains a release PR from conventional commits on `main`. Merging it creates the version tag and GitHub release. After CI passes, a maintainer approves the `npm` environment and the workflow publishes `@shadowclone/cli` with provenance.

Use `feat:` for a minor version, `fix:` for a patch, and `!` for a breaking change. The [release workflow](.github/workflows/release.yml) defines publishing and retry behavior.
