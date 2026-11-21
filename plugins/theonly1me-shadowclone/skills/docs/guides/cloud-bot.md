# Cloud bot

A cloud bot is Claude Code or Codex running in GitHub Actions on your repository, with your engineering skills. It works on issues, answers mentions, and reviews pull requests. You merge. Live installation qualification is pending.

The bot is a **machine account**, a GitHub account that you create and name, such as `octo-shadow`. GitHub allows one free machine account for each person. A personal GitHub App is the second option.

## Set up a machine account bot

Ask your agent: "Set up shadowclone cloud here with the bot octo-shadow." The agent calls the `shadowclone_bot` MCP tool. Or run this in the checkout:

```bash
shadowclone bot setup --bot octo-shadow
```

You need the GitHub CLI (`gh auth login`), administration access to the repository, and an active Shadowclone skills environment.

1. If the account does not exist, setup opens the GitHub signup page. Create it and run setup again.
2. Approve the skill files that setup will push to your private repository `<you>/shadowclone-skills`. An agent must ask you first.
3. Setup protects the default branch, pushes the skills, adds a read-only deploy key, invites the bot, and opens the setup pull request.
4. Sign in as the bot, create a classic token with only the `repo` scope, and add it to the `shadowclone` environment as `SHADOWCLONE_BOT_TOKEN`.
5. Add the secret for your agent to the same environment: `CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`), `OPENAI_API_KEY`, or `CODEX_AUTH_JSON` (the content of `~/.codex/auth.json` after `codex login`).
6. Merge the setup pull request.
7. Mention the bot once, so that its first run accepts the invitation.

Shadowclone never reads your tokens. `shadowclone bot status --repo owner/repository` lists the open steps from secret names. To update your skills, run setup again. It pushes only changed files and replaces the deploy key.

## Use Codex

Add `--engine codex` or choose Codex in the browser. The checklist then asks for `OPENAI_API_KEY`. `--codex-auth plan` uses your ChatGPT plan instead. It is experimental and needs a machine account bot. Each run stores the refreshed login in `CODEX_AUTH_JSON`, so runs on the repository wait for each other. If another machine uses the same login, add a fresh `auth.json` when the bot cannot sign in. A Codex review reads only the pull request checkout.

## Set up a GitHub App bot

Run `shadowclone bot setup` without `--bot` and choose **Use a GitHub App instead**. Review the skill files, register and name the App, and install it with **Only select repositories**. Setup rejects **All repositories**. It uploads the App key and opens the setup pull request. Add the agent secret and merge. A private App installs only on its owning account, so an organization repository registers it under that organization.

## Work on issues and pull requests

Create an issue as the installing owner. Its stated scope lets the bot plan, change files, run checks, commit, push, and open a draft pull request. The bot marks it ready when checks pass, it has no conflicts, and every review thread has an answer. A larger scope needs your decision.

Mention the bot on an issue or a same-repository pull request: `@octo-shadow` for a machine account, or `@shadowclone` and the App slug for an App. External users, unapproved authors, fork pull requests, and the bot's own comments cannot start work.

- It reports a check that waits for a human and does not run it again.
- A run works for up to 3 hours. When it stops, its last step commits the remaining changes as the bot and pushes them to the work branch, unless the request is paused.
- Each branch has a daily limit of ten worker runs.

When the last Actions run on the head of a managed pull request finishes, the bot resumes it once. Approved reviewer events can resume it too. The default reviewers are `coderabbitai[bot]` and `github-actions[bot]`, and findings from repository writers count. To change requesters, reviewers, or limits, edit both workflow configurations in a reviewed pull request.

It answers review threads as [delegated work](delegated-work.md#review-comments) describes. It never merges, releases, or force pushes.

## Review pull requests

The bot posts one review with the event `COMMENT`. [Reviews](reviews.md) lists the triggers and the checks. A review runs in five jobs. Only the acknowledge and publish jobs hold the bot or App token. The toolchain job runs the pull request code with no secrets. The model job holds only the Claude token or Codex login and never runs that code. With a Codex plan login, only its last step gets the bot token.

`reviewModel` in both workflow configurations chooses the model, by default `claude-opus-5-5` for Claude and `gpt-6.1-sol` for Codex. `reviewNetwork: false` turns off web search and page fetches. Reviews count toward the daily branch limit.

## Continue locally

1. Add the label `shadowclone:paused`. It blocks dispatch and cancels matching worker runs.
2. Run `gh pr checkout <number>`, then make and push your changes.
3. Remove the label when the bot can continue.

A pause on the original issue also blocks its issue branch. The worker checks the pause state again after it queues and before writes. A cancellation does not make an in-flight write atomic.

## Skills and credentials

The bot reads your skills and native rules from the private repository `<you>/shadowclone-skills`, with a read-only deploy key for each target repository. Setup redacts and path-checks the files first. The bundle is frozen, so later local changes do not update it.

The `shadowclone` environment holds `SHADOWCLONE_BOT_TOKEN` (or `SHADOWCLONE_APP_PRIVATE_KEY`), the agent secret, and the deploy key `SHADOWCLONE_SKILLS_KEY`. Only the default branch can use it. Setup keeps existing approval settings and rejects broader branch policies. Your GitHub plan must support environment secrets.

The environment trusts its default-branch workflows and the code that runs with its secrets. The coding agent gets the bot or App token, never the App private key, and can run any shell command on the runner. A machine account token has no `workflow` scope and reaches every repository that you invite the bot to. Invite it only to repositories that it works on.

Before it adds a secret, setup adds the `shadowclone default branch` ruleset, which restricts updates and deletion of the default branch. Setup stops if a ruleset with that name has other settings. The admin and maintain roles are exempt, and with an App the write role is exempt too. The bot has the write role, so with a machine account, write-role members in an organization repository need an admin or a maintainer to merge. Workflows that push to the default branch with `GITHUB_TOKEN` stop working, because GitHub Actions is not exempt.

`shadowclone bot export --skill shadowclone-work --skill shadowclone-baseline --output <private-folder>` saves the skills to a folder outside the checkout. It uploads nothing.

## Stop and remove

1. Pause the work and cancel remaining Actions runs.
2. Remove the two Shadowclone workflows and `.github/shadowclone/` in a pull request.
3. Delete the environment secrets, the ruleset, and the deploy key on your skills repository.
4. Remove the bot from the collaborators, or uninstall or delete the App.
5. Remove `~/.shadowclone/cloud/installations/` if you no longer need it.

Exported folders and your skills repository stay until you delete them. GitHub and the provider apply their own retention policies.
