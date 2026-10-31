# Contributing

Thank you for considering a contribution to planning-with-files.

This project keeps contribution work small, traceable, and reviewable. Please make one logical change per pull request and keep the tone concise and concrete.

## How to set up locally

Fork the repository, then clone your fork:

```bash
git clone https://github.com/YOUR-USERNAME/planning-with-files.git
cd planning-with-files
```

Add the upstream repository so you can sync your fork with the original project:

```bash
git remote add upstream https://github.com/OthmanAdi/planning-with-files.git
git fetch upstream
```

The canonical skill lives here:

```text
skills/planning-with-files/SKILL.md
```

Before opening a pull request, run the test suite:

```bash
python -m pytest tests/ -q
```

Investigate test failures and include any unresolved findings in your pull request description.

## CI completion rule

Maintainer delivery is complete only after all five `Tests` jobs succeed on the final commit pushed to `master`: pytest on Linux, Windows and macOS, plus the Pi extension and OpenCode plugin suites.

After the final push, verify the remote `master` commit and wait for its workflow to finish. Queued, running, cancelled, timed-out, failed or missing checks mean verification is unfinished. Continue investigating, fixing and rerunning until every job is green. Preserve test coverage and security checks; change runtime limits only when measured runtime justifies a bounded adjustment.

A passing candidate branch or an identical Git tree does not replace checks on the final pushed commit. Recheck remote `master` and its check results immediately before reporting completion. If the user explicitly stops the work or an external blocker prevents progress, record the unfinished checks and the blocker.

## Project layout

The canonical skill source is:

```text
skills/planning-with-files/
```

Language variants live under directories that follow this pattern:

```text
skills/i18n/planning-with-files-<lang>/
```

Keep them one directory below `skills/`. The Claude Code plugin scan reads `skills/*/SKILL.md` and does not recurse, so a variant placed directly under `skills/` is registered for every plugin user and its description is added to every session's system prompt. `tests/test_plugin_skill_surface.py` fails if that happens.

IDE adapter variants live under these directories:

```text
.codebuddy/
.codex/
.cursor/
.factory/
.hermes/
.mastracode/
.opencode/
.pi/
```

The `clawhub-upload/` directory is gitignored and handled manually. Do not rely on it as the source of truth for repository changes. For a release, run `python scripts/build-clawhub-upload.py`, then run `python scripts/build-clawhub-upload.py --verify` and require the complete folder to match the canonical tracked inventory. Manually upload the entire `clawhub-upload/` folder at clawhub.io.

## Submitting a PR

Use a focused branch name that describes the type of change:

```text
fix/short-description
feat/short-description
docs/short-description
```

Use Conventional Commits for commit messages:

```text
fix: describe the bug fix
feat: describe the new behavior
docs: describe the documentation change
```

Keep each pull request to one logical change. A documentation fix, a language variant update, and a test change should usually be separate pull requests.

When opening the pull request, include:

- What changed
- Why it changed
- How you tested it
- Any known limitations or platform-specific notes

If the pull request closes an issue, include the issue reference in the description:

```text
Closes #123
```

## Authorship and credit

The project maintains contributor credit in `CONTRIBUTORS.md`.

Merged pull requests earn a permanent contributor entry. Keep your Git author information accurate because your commits remain part of the project history and are not treated as disposable metadata.

Small contributions count. Documentation fixes, language variant updates, tests, and adapter improvements all help maintain the project.

## Language variant contributions

Translations and language variant improvements are welcome.

When working on a language variant, compare it against the canonical skill in:

```text
skills/planning-with-files/SKILL.md
```

Keep translated variants in parity with the canonical version. Do not ship a localized description with an English body stub. If a section cannot be translated yet, leave a clear note in the pull request instead of hiding incomplete work in the file.

## Where to ask questions

For general questions, use GitHub Discussions.

For issue-specific questions, comment on the relevant issue. If maintainer attention is needed, tag `@OthmanAdi` and describe the specific point you need help with.

Good questions include context, what you tried, and where you are blocked.
