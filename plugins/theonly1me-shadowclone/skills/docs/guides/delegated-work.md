# Delegated work

The `shadowclone-work` skill takes a request, an issue, or a pull request to a ready pull request. It works in your Claude Code or Codex session, with the permissions of that agent. The [cloud bot](cloud-bot.md) follows the same skill.

## Equip and invoke

1. Run `shadowclone wizard`, equip **Take Work to a Ready Pull Request**, and apply the build.
2. Start a new session and invoke the skill:

```text
/shadowclone-work Implement issue #31 and take it to a pull request that is ready to merge.
```

In Codex, use `$shadowclone-work`.

## What the skill does

1. It follows the format and checks in `README.md`, `CONTRIBUTING.md`, `AGENTS.md`, and the pull request template.
2. It builds the change with tests and opens a draft pull request.
3. It loops until every code check passes on the head, the branch has no conflict, and every review comment has an answer. It reruns a flaky job once and reports a check that waits for a human.
4. It marks the pull request ready, then checks once more for new comments.

## Review comments

- **Fix.** If a comment names a real defect or a reasonable in-scope request, the skill fixes it. Its reply is only the full 40-character SHA of the fix. It resolves a bot thread and leaves a human thread open.
- **Decline.** The skill declines a comment whose claim is false, asks to change documented behavior or for out-of-scope work, or is for another tool. It posts no reply, and the thread stays open.

It posts no other words and adds no attribution to titles, bodies, or commits.

## Branches and limits

Outside a stack, the skill merges the base branch in and never force pushes. In a [`gh stack`](https://gh.io/stacks) stack, it restacks with `gh stack rebase`, resolves conflicts, and pushes with `gh stack push`. It fixes a finding in the lowest pull request that owns the code. It never merges, closes, or approves a pull request.
