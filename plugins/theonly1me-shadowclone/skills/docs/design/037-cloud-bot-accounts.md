# Cloud bot accounts and setup on GitHub

## Problem

Cloud setup took many steps in a local browser wizard. The owner registered a GitHub App, pasted the Claude token into a Shadowclone page, and selected skills that had to fit in one GitHub secret. A secret holds at most 48 KB, so a larger set of skills could not reach the cloud. The bot also had no profile of its own. An App bot has no contribution graph, and people cannot mention it like a person.

## Decision

A cloud bot can be a **machine account**: a real GitHub account that the owner creates and names, such as `octo-shadow`. GitHub's terms allow one free machine account for each person. The personal GitHub App from [031](031-github-clones.md) stays as a second identity.

**Tokens stay on GitHub.** Setup creates the `shadowclone` environment, limited to the default branch, and opens its page. The owner adds each token there:

- `SHADOWCLONE_BOT_TOKEN` is a classic token with `repo` scope, which the owner makes while signed in as the bot. It has no `workflow` scope, so the bot cannot change workflows.
- `CLAUDE_CODE_OAUTH_TOKEN` comes from `claude setup-token`.

Shadowclone never reads either token. In App mode, setup still uploads the App key that the manifest flow returns, because Shadowclone creates that key.

**Skills live in a private repository.** Setup creates `<owner>/shadowclone-skills` as a private repository and shows the files that it will push. After one approval, it pushes them through the GitHub API. The files are the same plugin tree that the earlier secret held. The tree has the marketplace, the `shadowclone-personal` plugin with each skill, and `native.md`.

Setup makes a read-only deploy key on the skills repository for each target repository. It stores the private half as `SHADOWCLONE_SKILLS_KEY` in the target's environment. The worker checks out the skills repository with that key. So there is no size limit. Running setup again updates the skills.

**Setup is a checklist.** `shadowclone bot setup --bot <login>` and the MCP tool `shadowclone_bot` do each step that the owner's `gh` login can do:

1. Check administration access and the local checkout.
2. Invite the bot with write access.
3. Protect the default branch.
4. Create the environment.
5. Push the skills and add the deploy key.
6. Open the setup PR.

For each step that needs the owner, setup opens one GitHub page:

- The signup page, when the bot does not exist yet.
- The token page for the bot.
- The environment page for the two tokens.
- The setup PR.

`status` reads the names of the environment secrets, never their values. It also reads the PR state and the invitation. It lists what is still missing. The first worker run accepts the repository invitation with the bot token.

**The workflows choose the token by identity.** In account mode, every job that writes uses `SHADOWCLONE_BOT_TOKEN`, and the action commits as the bot. Its email is `<id>+<login>@users.noreply.github.com`, so merged commits count on the bot's profile. In App mode, the jobs mint an App token as before. A mention is `@<login>` in account mode. In App mode, `@shadowclone` and the App slug both work.

**The default branch stays protected.** The `shadowclone default branch` ruleset restricts updates and deletion of the default branch. In App mode, it exempts the admin, maintain, and write roles, as before. In account mode, the bot has the write role, so the ruleset exempts only the admin and maintain roles. In a personal repository, only the owner can update the default branch. In an organization repository, write-role members need an admin or a maintainer to merge, and setup says so.

**Long runs keep their work.** The work job stops at 180 minutes, and the agent step stops at 170 minutes. There is no turn cap. A last step runs even after a timeout or a failure. The step commits the remaining changes as the bot and pushes them. It does this only when the checkout is on the work branch and no one has paused the request. The work branch is never the default branch.

**Codex is the second agent.** With `--engine codex`, the worker runs a pinned Codex CLI with the skills in its home and the native rules as its `AGENTS.md`. An OpenAI API key signs in through `codex login --with-api-key`.

A ChatGPT plan login is experimental, and it needs a machine account:

- The job restores `auth.json` from `CODEX_AUTH_JSON`.
- It runs one job at a time for each repository.
- It writes the refreshed file back with the bot token, because Codex rotates the refresh token. If GitHub refuses the write, the job warns.

The Codex runner also returns a refreshed login to the user's Codex home after a local run, unless that home changed meanwhile.

A Codex review runs under its own permission profile. The shell can read only the checkout and the minimal system paths. It cannot read the Codex home or the run's temporary folder, and it has no network. The runner removes variables that hold keys, secrets, or tokens from its environment. Web search is live only when the review network is on.

## Consequences

- The owner creates a second GitHub account once, with its own email. GitHub can ask for 2FA. A paid organization charges a seat for it.
- The bot token reaches every repository that the owner invites the bot to. Setup invites it only to the target repository.
- An installation from an earlier version has no skills repository. Its `--cloud` request asks the owner to run setup again.
- The change removes the 48 KB limit and the guidance secret.
- A run that hits the time limit leaves a commit named `chore: save unfinished shadowclone work`, which a squash merge removes.
- An OpenAI API key bills per token. A plan login can stop working when another machine rotates its token. Then the owner adds a fresh `auth.json`.

## Verification

- Tests cover these areas:
  - The rendered workflows in each mode: tokens, the skills checkout, and no guidance secret.
  - The ruleset bypass in each mode.
  - The checklist from secret names, the PR state, and the invitation.
  - The skills push and the deploy key, with a fake `gh`.
  - An export larger than 48 KB.
- `actionlint` accepts the rendered workflows.
- Codex's own sandbox command confirmed on macOS that the review profile reads the checkout. The profile refuses the Codex home, the temporary folder, other home files, and writes.
- A live setup with a machine account on a private repository has this result. The owner adds the tokens on GitHub and merges the setup PR. Then `@<bot>` on an issue opens a PR with commits by the bot.

## Data handling

The skills and native rules go to a private repository that the owner owns. The same redaction and path checks as before apply to them. Tokens go from the owner's browser to GitHub. Shadowclone keeps only installation metadata under `~/.shadowclone/cloud/installations/`.
