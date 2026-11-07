# Pull request reviews

Shadowclone reviews a pull request against the standards of its own repository. Code collects the facts and runs the mechanical checks, and the `shadowclone-review` skill does the judgment.

## Review on this machine

```bash
shadowclone review 123
```

A small pull request takes about 1 minute. It writes a Markdown file to `~/.shadowclone/reviews/<owner>-<repository>/` and prints its path. `--output` chooses another file.

You need the GitHub CLI signed in with `gh auth login` and Claude Code signed in. The review uses your Claude subscription. `--model` chooses the model (default `claude-opus-5-5`), and `--effort` sets the reasoning effort. The reviewer searches the web and fetches documentation when a claim depends on library behavior. `--offline` turns that off. It uses temporary worktrees and leaves your checkout unchanged.

## Review a branch before you open a pull request

```bash
shadowclone review --base main
```

Without a number, the review reads the commits on the current branch since it left `--base` (default `origin/HEAD`). The commit messages replace the title and description. Commit first: the review leaves out uncommitted changes and says so.

## Review in the cloud

```bash
shadowclone review 123 --cloud
```

This posts the comment `@shadowclone review`, which only an App bot answers. For a machine account bot, comment `@<bot> review` yourself as the first line of a comment on a same-repository pull request. Your [cloud bot](cloud-bot.md) posts one review as itself and never approves or requests changes.

A pull request that a requester opens or marks ready gets a review without a comment. Drafts, forks, outside authors, and the bot's own pull requests do not. The first `--cloud` run sets up what is missing. It opens the setup page if you have no bot, or a draft pull request that updates the bot workflows. Merge that pull request, then run the command again.

## What the review checks

- **Standards:** `AGENTS.md`, `CLAUDE.md`, `.claude/rules`, repository skills, `CONTRIBUTING.md`, Copilot and Cursor rules, and `.shadowclone/harness.json`, read from the base commit.
- **Built-in rules:** 67 rules and nine credential patterns on added lines. They cover credentials, conflict markers, injection, unsafe deserialization, disabled TLS checks, weak hashes, risky workflows, and infrastructure settings.
- **Dependencies:** packages that a changed lockfile adds or upgrades, checked against the OSV vulnerability database.
- **Toolchain:** the type checks, compilers, and linters of the repository for JavaScript and TypeScript, Python, Go, Rust, Java, and .NET. Only the diagnostics that the pull request adds stay.
- **Judgment:** the skill traces each change through its callers and tests. A fresh refuter subagent tries to disprove each candidate finding before you see it.

A certain rule, such as a committed credential, needs no model. Other rule hits and toolchain diagnostics reach the review only when the skill confirms a real failure. A review reports at most ten findings, highest severity first.

## Evidence

Each finding quotes its evidence: code at the head, a line of the diff, a rule hit, a toolchain diagnostic, or a documentation passage. Code checks each quote against its source and leaves out a finding whose code quote does not match. The local review lists it as "Left out" with the reason.

Each rule hit and toolchain diagnostic that needs judgment gets an id. The reviewer must raise it in a finding or drop it with a reason, and the local review lists every dropped one. If a quote fails or an id has no decision, the reviewer gets one round of correction before code drops anything.

## Untrusted pull requests

The toolchain runs the configuration of the pull request, such as an ESLint config file, with dependency install scripts off. A local review runs it as you, so add `--no-checks` for a pull request from someone you do not trust. The built-in rules and the skill still run, because they only read the code. In the cloud, the toolchain job has no secrets.

## Limits

- The toolchain finds stacks from files at the repository root, so a monorepo without root manifests gets no toolchain checks.
- The review skips a tool that you did not install. The cloud runner has the six runtimes but not every linter.
- The review does not run the repository tests.
