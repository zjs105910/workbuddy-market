# Data handling

Shadowclone reads the sources that you enable and maintains local coding-agent guidance. It has no hosted collection service, analytics, crash reporting, or automatic upload of your environment. Model work uses your installed, authenticated agent CLI, under the account and retention terms of its provider.

## Consent

Source settings live in `~/.shadowclone/config.toml` and default to off. Default setup names detected paths before it asks about session access, skill maintenance, and background learning. `init --advanced` offers a choice for each source. Managed policy can restrict these settings.

Before consent, setup checks only whether a configured source root exists and has data. It keeps a temporary boolean and opens no source contents or entry names. Reading contents needs the matching setting.

Source access does not authorize automatic skill edits. Disabling a source removes its indexed events from later learning selection, and Shadowclone checks authorization again before each text reference resolves. Pending approval checks its saved provenance against current consent. Disabling a source does not erase published guidance or requests that a provider kept. Review and retire existing guidance separately.

## Sources

| Setting                  | What may be read                                                                                                                                                                             |
| ------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `claude-code`            | Session JSONL under `~/.claude/projects/`                                                                                                                                                    |
| `claude-prompts`         | `~/.claude/history.jsonl`                                                                                                                                                                    |
| `codex`                  | Sessions under `~/.codex/sessions/`, or `$CODEX_HOME/sessions/`                                                                                                                              |
| `cursor`                 | Chat databases and metadata under `~/.cursor/chats/`                                                                                                                                         |
| `pi`                     | Version 3 session JSONL under `~/.pi/agent/sessions/`, or `$PI_CODING_AGENT_DIR/sessions/`. Original files stay untouched                                                                    |
| `antigravity`            | Generated conversation logs under `~/.gemini/antigravity-cli/brain/`                                                                                                                         |
| `antigravity-workspaces` | `~/.gemini/antigravity-cli/history.jsonl`, for workspace attribution                                                                                                                         |
| `declared-rules`         | Repository-root `CLAUDE.md`, `AGENTS.md`, `.cursorrules`, and direct `SKILL.md` files under `.claude/skills/` and `.agents/skills/`                                                          |
| `claude-rules`           | Markdown rules under the current repository's `.claude/rules/`, for compatible native guidance                                                                                               |
| `claude-memory`          | Claude memory under `~/.claude/projects/<repo>/memory/`. Recurring extraction needs registered repositories with verified identity                                                           |
| `agent-context`          | Selected-agent personal instructions and skills, kept as an original baseline and copied into evaluation arms                                                                                |
| `skill-library`          | Consented personal, repository, custom, and third-party skill roots                                                                                                                          |
| `git-metadata`           | Local repository remote names, to determine scope                                                                                                                                            |
| `github-writing`         | Through your `gh` login, for voice capture only: your 40 newest pull request titles and bodies, your 40 newest reviews with up to 10 comments each, and your 60 newest commit messages       |
| `repository-manifests`   | Scripts and dependency names in `package.json`, lockfile names, `pyproject.toml`, `requirements.txt`, `Makefile` targets, CI workflow files, and top-level entry names, for repository setup |

Shell history is not a source. Upgrading deletes indexed shell history events, cursors, and repository bindings, and Shadowclone ignores a `shell` setting left in an older `config.toml` or managed policy.

Personal skill locations include `~/.agents/skills/`, `~/.claude/skills/`, `~/.codex/skills/`, `~/.cursor/skills/`, and `~/.gemini/config/skills/`. Shadowclone may also review configured provider plugin caches. Codex paths follow `$CODEX_HOME` when set. Evaluation context can include `~/.claude/CLAUDE.md`, Codex `AGENTS.md` and `AGENTS.override.md`, and the selected skill catalog, which each study freezes.

Transcript parsers can meet prompts, assistant responses, tool results, and thinking blocks in an enabled file. Only user-authored text counts as learning evidence. Tool results, tool-returned file contents, thinking, and data-access results never enter learning. Agent responses, plans, and questions reach the model only as labeled context beside a user correction. Eligible text can still hold sensitive information.

Pi transcript consent is separate from Git metadata and skill maintenance. Session start records repository identity only when both Pi capture and Git metadata are on. See [capture](architecture/01-capture.md) for what each adapter excludes.

## What reaches a model

| Operation                   | Provider access                                                                                                                              |
| --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| Plain `learn` after setup   | Local indexing and reporting. No model calls                                                                                                 |
| Deep or background learning | Selected redacted steering, supporting context, and guidance needed for reconciliation                                                       |
| Skill maintenance           | Redacted catalogs, full instructions of overlapping workflows, and evidence for proposed updates. Supporting resources are checked locally   |
| Browser editor              | Opening it makes no model request. Build naming sends redacted skill titles and summaries. Voice capture and skill drafts need a user action |
| Cloud bot                   | Reviewed skills from your private skills repository, the selected repository, and an authorized issue or PR task                             |
| `shadowclone-work` skill    | The existing agent session reads the skill and its own workspace. Shadowclone makes no model calls                                           |
| Pull request review         | The PR title and description, diff, file history, base-commit standards, rule hits, toolchain diagnostics, and files that the reviewer reads |
| Evaluation                  | Synthetic task workspaces and the tested setup's skills and instructions. Judges receive generated code without redaction                    |

First-time interactive `learn` can offer setup, which may make an authorized first learning pass. A deep dry run still calls a model.

Pi learning sends only prepared redacted input, with no tools or coding-session context, over a private token-authenticated socket or temporary private files. Pi keeps provider configuration and credentials. A missing live bridge or model fails with no provider fallback.

Eligible source text crosses the shared redaction boundary before learning or context import. Redaction detects known token, host, path, and entropy patterns. It can miss confidential prose, personal information, and unusual secrets, and it can remove harmless text. It is not an anonymity guarantee. Use only material that you may send to the chosen provider. Provider limits or charges may apply, and local deletion does not delete provider copies.

## Local files

Earlier versions kept delegated task records under `~/.shadowclone/runs/`, grants under `~/.shadowclone/task-grants/`, and task worktrees under `~/.shadowclone/worktrees/`. Shadowclone no longer creates them. `forget --all` stops while old worktrees remain, so it deletes no unfinished change. Move or remove them yourself.

| Location                                | Contents                                                                                                                             |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `~/.shadowclone/config.toml`            | Source consent and model and action settings                                                                                         |
| `~/.shadowclone/environment.json`       | Learned guidance, scope, evidence, publication decisions, and builds                                                                 |
| `~/.shadowclone/index.db` and sidecars  | Event metadata, source references, cursors, and origin bindings                                                                      |
| `~/.shadowclone/profile/`               | Legacy profile state and recovery artifacts                                                                                          |
| `~/.shadowclone/distill/`               | Derived learning checkpoints and fingerprints                                                                                        |
| `~/.shadowclone/learning-pending.json`  | Learned rules awaiting approval, with source provenance and keys rejected during review                                              |
| `~/.shadowclone/learning-attempts/`     | Private receipts with outcome codes, counts, and next actions, without excerpts or transcript paths                                  |
| `~/.shadowclone/learning-feedback.json` | Opaque evidence hashes, rule and guidance identifiers, source names, correction times, and review acknowledgements                   |
| `~/.shadowclone/learning-probes/`       | Probe receipts with task and guidance hashes, provider metadata, outcomes, and loading observations, without prompt or response text |
| `~/.shadowclone/skills.json`            | Configured roots, maintenance ownership, and cached library review fingerprints                                                      |
| `~/.shadowclone/skill-proposals/`       | Proposed edits and conflicts with redacted supporting passages and required decisions                                                |
| Other files under `~/.shadowclone/`     | Revisions, installation ownership, original-library snapshots, and learning and skill ledgers                                        |
| Agent skill and instruction directories | Published skills, resources, native routing, and hooks                                                                               |
| Repository harness files                | Reviewed shared instructions, skills, and checks meant for version control                                                           |

Shadowclone does not copy whole transcripts into its store. The index holds references and event metadata. Learning records, checkpoints, and original-library snapshots can still hold sensitive derived content. State uses private directories and owner-only permissions where supported, and it is not encrypted. Processes with equivalent access, administrators, and backups may read it. Interrupted evaluation can leave temporary workspaces in its private study directory for manual cleanup.

## Scope and editing

Repository learning stays with the registered repository. Setup and deep learning register the working repository only when Git-metadata consent and skill maintenance are on and its remote identity verifies. Past sessions from before metadata consent stay isolated until you confirm a directory-to-remote association. Blocked and unknown origins stay unregistered. Organization learning uses a normalized remote-owner identity, which is a technical scope and does not verify a legal employer boundary. Explicit global guidance applies across repositories. Guidance that names a repository, codebase, or path never gets global scope, even when the learning model rates its evidence as global. Without Git-metadata consent, working directories stay isolated.

Automatic skill maintenance needs separate write authorization. Conflicting edits stay pending. Before a model sees a learned rule from captured sessions, a local check looks for text that reads like instructions to an agent. It flags:

- A request to ignore other instructions.
- An imitated system or role message.
- A download piped into a shell.
- A request to send secrets.
- Hidden or direction-changing characters.
- A long encoded string.

A flagged rule stays pending with its reasons, and nothing publishes it. The check skips rules that the user wrote or chose. Native memory and third-party packages stay unchanged. Revisions record files together and refuse an undo that would overwrite later edits.

## Execution

Outside personal GitHub clone setup and pull request reviews, Shadowclone does not commit, push, or act on GitHub itself. The `shadowclone-work` skill acts through the host agent's own tools and permissions. A push sends Git objects, including repository code, without redaction. Review comment text is untrusted data and never becomes learning input.

A local pull request review fetches the PR refs, reads them in temporary worktrees, and removes the worktrees afterwards. Its toolchain checks run the PR's own configuration as you, with dependency install scripts off and only tool-related environment variables. `--no-checks` skips them. The review model can read only files inside the head worktree. Unless you set `--offline`, it can search the web and fetch pages with GET requests. The skill tells it to put only public names in searches and URLs. Shadowclone then fetches each cited documentation URL itself to check the quote, with GET only and private, loopback, and metadata addresses refused. Unless `--offline` is set, the names and versions of packages that a changed lockfile adds or upgrades go to the OSV API, without code. `--cloud` posts one `@shadowclone review` comment as you, and the clone posts the review. Cloud review results pass between jobs as artifacts that expire after one day. Posted text is redacted, and mentions and cross-repository links are wrapped in code spans. Review output never becomes learning input.

The pull request review evaluation copies merged pull requests from a public repository into a public evaluation repository and keeps the source license. Copied descriptions lose mentions and links to the source threads, so no upstream author is notified. The evaluated reviewers run on that repository with the owner's accounts. Raw runs, judge verdicts, and the case list stay in private storage outside every checkout until publication.

Evaluation confines candidate writes to disposable workspaces, with separate workspace and agent-home copies. Native filesystem policies deny credential reads and network access. Authentication is copied for the selected CLI and removed in cleanup. Verification runs apart, without provider credentials or network access, and sends no verifier output to judges. These controls depend on the supported provider and operating-system sandbox. The [architecture](architecture/README.md#delegated-work) and the [evaluations](../evals/README.md) describe their contracts. Native Codex evaluation denies shared `/tmp` and `/private/tmp`. Claude's native sandbox still needs separate host qualification.

Scored execution sends the synthetic repository, prompts, and selected guidance to the selected provider. Responses, code, traces, frozen inputs, learning receipts, scores, raw native stdout and stderr, and identifying runtime paths stay in private storage outside every checkout. They stay out of public reports and every learning source. Public synthetic inputs include fixed correction sessions with synthetic repository bindings. Preparation replays them through the normal index API and never associates a user's unbound history with a current remote.

The browser editor listens on loopback, serves local assets, checks request origins, and uses an ephemeral token. Opening it grants no new capture consent.

Skill discovery reads only configured, consented roots. It allows up to 2,000 distinct physical skill files and 8 MB in total, and counts overlapping roots once. Native copies may collapse into one browser entry. A skill keeps its 48 KB and 500-line limits, and discovery refuses paths nested more than twelve levels.

Build naming sends the redacted titles and one-line summaries of the equipped skills and preferences. It never sends skill bodies, paths, repository names, or ownership metadata. It makes one call to the fast tier of the engine, with no tools and a 30-second deadline. Where the provider supports a dollar cap, the limit is $0.05. **Turn naming off** stores the choice in that browser and stops every naming request. Results stay in server memory until the editor closes. [Agent builds](guides/agent-builds.md#your-build-name) lists the timing and models.

Voice capture needs the `github-writing` setting, which the **My voice** dialog turns on or off. Managed policy can block it. With the setting off, the editor makes no `gh` call. Capture reads only text that the signed-in user wrote. It skips pull requests from `codex/`, `claude/`, and `cursor/` branches, text with agent attribution lines, release pull requests, and merge and revert commits. It removes fenced code, comments, and images, redacts each item through `redactSecrets`, and keeps at most 1,200 characters per item and 24,000 in total. One call to the saved learning model describes the voice and writes 3 invented examples. The call has a 120-second deadline and a $0.25 limit where the provider supports a dollar cap. A result that copies 8 or more words in a row from the writing is discarded. Rewriting the examples after an edit sends only the edited description to the fast model. Collected writing stays in server memory until the editor closes or you turn the setting off. Saving writes `~/.agents/voice.md` only when no file or link exists there.

**Use AI** in the skill editor sends only the typed form fields and reads no repository file. The request uses the learning execution contract with no tools, one call, and a 60-second deadline. Providers with dollar-cap support get a $0.25 limit. Other providers show that no cap can be enforced. Cancellation aborts the request, but usage already incurred may still be charged. Generated drafts stay editable and need the usual build review before publication.

## Personal GitHub clones

`bot setup` authorizes a read of the current repository origin for that setup and does not turn on ongoing Git metadata capture. Managed source, engine, blocked-origin, and action restrictions still apply. The browser previews the selected scoped skills, resources, plugin metadata, and native rules through the redacted delivery boundary. It excludes transcripts, source history, receipts, and raw learning records. Uploading guidance and using the subscription need your approval of the exact preview in the local browser.

You do the App registration and installation in your own GitHub browser session. MCP can start setup or return saved status, and it has no activation or credential operation. Setup never extracts an existing interactive credential. You paste the `claude setup-token` credential into a loopback password request, and the GitHub CLI receives secrets through stdin. App registration credentials and the preview stay in server memory until shutdown. Non-secret installation metadata lives under `~/.shadowclone/cloud/installations/`. Explicit exports use owner-only files outside the checkout and stay until you delete them.

Cloud tasks and exported guidance are not new learning sources. Local guidance changes do not update the frozen cloud bundle. The [cloud bot guide](guides/cloud-bot.md) covers secrets, the default-branch ruleset, who can start work, pausing, installation, limits, and removal.

## Boundaries that a change must keep

Contributors also read the [contributor data rules](../.claude/skills/data-handling/SKILL.md).

- `resolveRedacted` turns an eligible pointer into text only after it checks the range, the root, the file type, the limits, and the captured identity. `materializeSnapshot` uses the same redaction, so model text matches the parsed metadata.
- Persistent identities stay local behind opaque tokens during reconciliation. Logs show counts, sizes, hashes, and source names. Captured paths and raw provider output must not become diagnostic text.
- Resource copies keep their bytes and permissions. Local checks cover them. Maintenance never sends them to the learning model and never runs them. A symbolic link, an unsafe reference, or an exceeded limit stops the update.
- Shared repository files are visible to anyone with repository access and can publish personal guidance, so review them before you commit. Setup asks before it includes personal guidance. Browser previews check the observed files again before they apply a change.
- Learning, authorized coding runs, and evaluation have different input contracts. Learning makes a request with no tools and shared limits. A coding run exposes a worktree to the provider. Evaluation exposes synthetic workspaces. Keep them apart.
- Candidate writes and verification have separate operating system restrictions. Unknown spend or missing required isolation stops the affected workflow.
- Pi dispatch and Pi evaluation stay disabled, because their action restrictions are not qualified.

## Retention and removal

There is no automatic expiry policy. Use `learning disable` to stop background learning and source settings to stop future reads. Use `skills automatic off` to stop automatic skill edits. Review active guidance with `learning list`, `learning show`, or `context --explain`, and reverse a revision with `undo`. `learning retire`, `replace`, `narrow`, and `remove-source` preview explicit changes before application. Source removal keeps mixed-source and unresolved records for single review and never removes original transcripts or memory.

`uninstall --global` removes recorded global integrations, and `uninstall --local` removes recorded integrations in the current repository. Ownership checks keep unrelated content and refuse conflicting managed edits. Legacy artifacts without ownership records may need manual removal.

`shadowclone forget --all` restores or removes recorded managed files and deletes the local state of Shadowclone, including task worktrees and original snapshots. Preserve unfinished work first. A conflicting maintained file can stop the operation before it completes.

Original transcripts, native memory, provider-retained requests, external repositories, backups, remote branches, PRs, Git history, and repository harness files remain. Use `undo` before you delete revision history, or remove harness files through version control. There are no source-specific or repository-specific forget flags.

## Managed installations and reports

Root-owned managed policy can disable Shadowclone or restrict sources, engines, origins, and action tiers. It governs this installation, not other programs under the same account. `local-only` blocks hosted learning, and no local model engine exists.

Report exposures privately through [security reporting](../SECURITY.md). Public reports should hold synthetic examples and reviewed summaries, never raw transcripts, private receipts, credentials, or identifying paths.
