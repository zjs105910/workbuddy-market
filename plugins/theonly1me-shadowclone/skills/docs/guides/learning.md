# Learning

Shadowclone learns reusable instructions and corrections from the sources that you enable. Learning with a model needs an installed and configured `claude`, `codex`, `cursor-agent`, or `pi` CLI. Antigravity supports capture and native guidance only. For Pi, see [Pi setup](pi.md). Run `shadowclone init --advanced` to choose the sources that Shadowclone can read.

## Run deep learning

```bash
shadowclone learn --deep
```

Shadowclone compares eligible evidence with your existing guidance and proposes changes for you to review. The model merges overlapping rules, and each new rule ends up merged, kept, or dropped with a reason. Press Enter at the review prompt to leave rules pending.

Each run allows up to 20 model calls and 5 minutes. The first pass in interactive setup allows 12 calls and 90 seconds. Run it again if the result says that more history remains. `--dry-run` previews and still calls the model. `--apply` skips the confirmation prompt. `--engine`, `--model`, and `--reasoning-effort` choose the engine, model, and effort. `--max-calls <n>` sets the call ceiling.

Plain `shadowclone learn` indexes and reports on your machine, with no model call. On Linux, Claude Code learning needs `bwrap` and `socat`, and Shadowclone names any missing command.

## Review learned rules

`shadowclone learning pending` lists learned proposals, scope blockers, publication work, and skill conflicts. `learning show <key>` displays the rule, its proposed replacement, scope, redacted excerpts, capture sources, and delivery state, but no excerpt from a disabled source. Decide with `learning apply <key>` or `learning reject <key>`.

Approval records the rule and tries to publish it in its scope, within the learning budget. It can call the model to edit a skill, and it does not run extraction again. Publication can still need a repository scope or a conflict decision.

- If a skill draft fails validation, the model gets one repair turn with the exact error. If the repair fails or no learning call is left, the rule stays pending with both errors.
- If a source that supports the rule is now disabled, the rule stays pending.
- If a learned rule reads like an instruction to an agent, such as "ignore all previous instructions", Shadowclone holds it before any model sees it. `learn` prints the count. Rewrite it with `learning replace`, or remove it with `learning retire`.

`learning status` shows the latest private attempt receipt. Start a new agent session after a rule becomes active. Publication confirms installation, not compliance.

## Background learning

Background learning has its own consent. After `shadowclone learning enable`, Shadowclone classifies eligible steering inside the same bounded execution as manual learning. A temporary exception or an interruption alone never becomes a standing preference, and cue words need not be English. `learning disable` turns it off.

## Record a rule

`shadowclone remember --repo "Use complete variable names."` records repository guidance yourself. Use `--global` only for guidance that applies to every repository. Recording and publishing are separate steps. `shadowclone skills pending` shows the publication work, and `shadowclone context --explain` shows active guidance.

## Link past sessions to a repository

Sessions indexed before you gave Git metadata consent stay isolated. After you give that consent, setup offers each verified link from a past directory to a remote for review. To review the candidates later, run `shadowclone learning repositories`, then `shadowclone learning bind <id>` and `shadowclone learn --deep`. Only the confirmed directory group gets the binding, and a changed remote invalidates it. Binding does not make a repository rule global.

## Change or retire guidance

Preview each change:

- `learning narrow <key>` moves global or owner-wide guidance into the current verified repository. It never widens a scope.
- `learning replace <key> "Use complete words in release notes."` makes the typed guidance your direct decision and clears the conflicting proposal.
- `learning retire <key>` retires the rule.
- `learning remove-source codex` retires records that only that source supports and rejects pending proposals with that provenance. Mixed-source and unresolved records stay for single review. Original transcripts, memory, and skills stay.

These commands write nothing until you repeat them with `--apply --expected <fingerprint>` and the printed fingerprint. If learning changed in the meantime, apply stops so that you can review again. Each decision has a revision that you can read with `history` and reverse with `undo`.

## Review later corrections and test a response

`learning pending`, `show`, and `status` flag durable corrections that matched a rule after its publication. A count asks for a review and does not prove that the agent ignored the rule. Run `learning acknowledge <key>` to mark them reviewed.

On macOS, `shadowclone learning probe <key> --agent codex --task "Is the sample ready?" --expect "READY" --yes` runs one isolated Claude Code or Codex session against redacted snapshots of the installed native guidance. Publish the guidance first, and choose a synthetic task and the exact response that shows your rule at work. `--yes` authorizes one paid call with a 60-second deadline. The probe uses a disposable home, read access, no memory, and no hooks. Its receipt, which `learning probe status` shows, holds no task or response text. A pass proves only that one response matched.

See [data handling](../data-handling.md).
