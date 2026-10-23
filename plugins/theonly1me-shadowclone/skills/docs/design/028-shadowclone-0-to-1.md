# From a correction to active guidance

## Problem

A user can consent to learning and correct an agent. Even so, the next session can start without that correction in usable guidance. Indexed events from a newly disabled source can reach learning. Codex user text can enter the index without becoming a learning excerpt. Shadowclone marks a declined manual proposal as processed without a pending decision. Historical sessions often have no verified repository identity, so repository guidance stays deferred. Native routing can point Claude at a skill path that Claude cannot read. It can repeat the same text through hooks. It can place personal absolute paths in repository files.

The preference study has separate reporting defects. Unknown checks lower the headline rates but disappear from the detailed counts. The bootstrap samples checks instead of complete sessions. The README omits the existing-skills arm that the scored environments include. Resolve these defects and the narrow study before you make stronger outcome claims.

The intended user result is one visible sequence:

1. Identify a reusable correction.
2. Review its evidence and scope.
3. Approve the exact guidance change.
4. See where it became active.
5. Undo or revise it later.

Publication, observed loading, and demonstrated behavior are separate facts.

## Decision

### Delivery contract

The active environment owns one versioned preference record. It also owns the evidence and source provenance of the record, its review decision, and the artifacts that come from it. The environment stays the only active write path. Shadowclone renders a short scoped preference directly into the matching native instruction surface of Claude Code and Codex. A skill holds the complete rule or procedure. The agent selects the skill by name and description when the task needs its detail. The native text does not require an unconditional file read. It does not contain an absolute personal path. Existing skills stay the baseline. Each bundled workflow is optional.

Each publication revision contains skill or resource changes, native text, environment delivery decisions, and destination fingerprints. Shadowclone records review decisions first. Then a later model or publication failure leaves a durable decision that it can retry. A successful approval attempts scoped publication and refreshes installed integrations in the same operation. If a destination changed after the preview, publication stops with an actionable pending reason and keeps the prior files. History keeps the decision and the later publication revisions as separate entries for undo. The result reports the active scopes and whether the user needs a new agent session. A declined confirmation stores a pending proposal. An explicit rejection stores a rejection, so later learning does not silently recreate the rule.

Global rules go only to global native instructions. Repository rules go only to a registered matching repository and its private local instruction files. Shared repository instructions need an explicit shared build preview and use relative references. Personal repository publication must not create untracked `AGENTS.md` or `CLAUDE.md` files that contain home paths. The native adapter of each agent owns the destination and the formatting. The environment owns rule selection and precedence. Hooks keep their capture and session metadata duties. They do not repeat native guidance that the agent already loaded from files. Hook commands resolve to the installed executable at integration time. Synchronization refreshes them.

### Consent and evidence

Create one eligible-event selector for manual, setup, and background learning. It filters indexed events against the current effective source configuration and managed policy before signal derivation. The model-facing path that reads the text checks authorization again before it resolves each reference. The index can keep old pointers, but a disabled source supplies no new learning text. Existing published guidance remains until the user selects a separate reviewed source-removal operation, as the current data policy documents.

Normalize provider records to typed user-text references before prompt extraction. The Codex normalizer reads `response_item.payload.content` blocks of type `input_text`. Claude keeps its supported user content forms. Both reject tool returns, tool-returned file data, thinking, and data-access results. Text still goes through `resolveRedacted`. Normalized records hold pointers. They are not another raw transcript archive. Contract tests must follow the same adapter, index, selection, redaction, reconciliation, and publication path that the CLI uses.

Historical repository binding is a user decision. With Git-metadata consent, show the candidate historical working-directory groups next to their current verified remote identity. Ask for an explicit mapping. Record the confirmed binding and its provenance in the index. An absent, blocked, or changed remote stays isolated. The mapping never creates global evidence. When the user removes a source, provenance previews the guidance that only that source supports. Mixed-source guidance needs review before the change to a shared skill.

Binding must also reconsider only the affected episodes in the learning ledger. Before you write a binding, do these steps:

1. Derive the existing episode identifiers of the candidate group from its indexed events.
2. Remove the matching processed entries.
3. Bind the origin keys of the group.

Unrelated ledger entries stay unchanged. A later learning run can reconcile those episodes under the newly confirmed repository scope. The binding command reports how many episodes became eligible again.

`learning/provenance.ts` maps supporting evidence identifiers to the indexed text references of the signal. It saves the named capture sources and the completeness. Pending approval reads the current effective source configuration again and checks that provenance. Missing provenance, or a source disabled since learning, blocks approval and leaves the rule pending. Active environment records keep the same provenance. The user can reject a pending rule, re-enable its source, or learn again from authorized evidence. This check governs the approval of a new proposal. Disabling a source does not silently delete guidance that Shadowclone already published.

`learning/catalog.ts` shows pending review, scope blockers, skill proposals, and active records through `learning list`, `pending`, and `show`. Evidence display resolves only currently consented indexed user episodes, through the existing boundary that resolves redacted text. `learning/lifecycle.ts` previews record replacement, retirement, repository narrowing, and source removal. Preview fingerprints protect the reviewed environment state. Narrowing retires the old key and creates a distinct scoped key. Then Shadowclone can reconcile the old and new destinations independently. Retirement records a rejection state, to prevent silent recreation. Source removal retires only complete single-source records and rejects matching pending proposals. Mixed or unknown provenance needs individual review. Scoped publication accepts explicit learning keys and preserves the automatic-maintenance setting. It skips unrelated memory extraction and library conflict scans.

### Learning service and lifecycle

Move engine selection, bounded execution, reconciliation, persistence, and publication coordination from `cli/deepLearn.ts` into a service under `learning/`. CLI commands format output and ask for confirmation. The background worker supplies its previously authorized automatic decision. Keep legacy profile reads and writes behind migration adapters. Select active environment storage explicitly, not through misleading profile-named entry points.

Manual learning works when the user consented to learning. It does not depend on background improvement. Background improvement stays a separate consent flag. The background path uses the same evidence and durability classification as manual learning, within its existing time and call limits. An English keyword is not an eligibility requirement.

Shadowclone marks an episode processed only after its reconciliation result is durable. The result must be an active record, a pending proposal, an explicit rejection, or a recorded no-change reason. A failure before that point leaves the episode retryable. A private attempt receipt records an opaque attempt id, source and episode counts, and time and engine metadata. It also records bounded outcome codes, proposal and publication ids, and a safe next action. It stores no raw excerpt or identifying transcript path. User-facing outcomes distinguish no eligible evidence, already covered, and uncertain or conflicting evidence. They also distinguish missing scope, awaiting review, published guidance, and engine or publication failure. The background worker saves a safe failure category instead of only `failed`.

Preference state says whether a rule is candidate, pending review, active, or retired. Delivery state separately records pending, published, covered, or blocked destinations. Observation state separately records whether an agent loaded the guidance or whether a requested behavior probe passed. A user can narrow, replace, reject, retire, and undo from one review surface. The existing advanced commands stay available. A later correction to an active rule raises a review signal. It does not silently rewrite the rule. Source-specific removal previews the affected records and artifacts. It uses the same ownership and undo machinery.

### First use and diagnostics

`shadowclone` without arguments shows the current setup state and one next action. `init` keeps its explicit consent choices. The browser and terminal review surfaces show a learned rule, the supporting redacted evidence, the scope, the exact proposed change, and the destination. Applying the change completes synchronization. If the user takes no action, a durable pending item stays. Diagnostics report installed, loaded when observable, and behavior-checked separately. They also name missing sandbox prerequisites before a model run. They bound provider error output, so the terminal does not print bundled source code.

The first-run message reports how many rules the system learned, how many are active, which need review or scope, and when to restart the agent. It never treats learning as proof of delivery. It never treats delivery as proof of compliance. The default build keeps existing guidance. It does not automatically equip the generic bundled workflows.

### Evaluation and public claims

Adherence denominators and counts exclude unknown and not-applicable checks, but their totals stay visible. An infrastructure failure before any agent action has no scored outcome. A run with agent action keeps its observed checks, and the report lists missing checks as unknown. Each observation keeps a session identity. The bootstrap draws tasks, then complete sessions within each drawn task and arm. Every check from a sampled session moves together. A paired arm difference uses the same task draw. Synthetic fixtures cover correlated checks and error handling.

Reply scoring recognizes a fenced reply, a quoted reply, or a conventional reply label before a reply body. Ambiguous extra prose stays visible. The scorer does not guess it away. Sentence counting protects common abbreviations. Review the private forbidden-pattern definitions in the private study directory. Do not copy them into this checkout. Reports name the product revision and the scorer version for every reused run group. The disclosure about evaluation preparation states that the system applied nonconflicting proposals automatically. It states that this is an upper-bound delivery condition relative to ordinary review.

Regenerate the published aggregate from private receipts after the scorer and bootstrap fixes. If the receipts are not available, remove the numerical headline until someone can recompute it. The README includes all four arms. It leads with deep learning over the participant's existing skills. It does not describe point-estimate differences whose intervals include zero as established gains. Disclose these limits: one participant, one repository, tasks reused after product fixes, and the decision about the headline view after the results. Freeze future tasks before coverage analysis. A later held-out study needs separate authorization. It uses new users, repositories, and tasks. It tests conflicting and temporary preferences and irrelevant guidance. It measures repeat corrections and interventions, together with adherence and task correctness. Claude Code and Codex are the evaluation targets for this work.

## Implementation sequence

`learning/maintenance` owns the choice between active environment maintenance and legacy library maintenance. Active CLI and worker callers use that service directly. `skillMaintenance/legacyUpdate` contains the legacy implementation. The old exported update API stays as a small compatibility forwarding module. Environment modules reuse discovery and synchronization primitives. They do not reuse the compatibility coordinator. This removes the ambiguity about package-level ownership. It does not replace the publication safeguards.

1. Add the shared authorized evidence selector and provider user-text normalization. Prove revocation after indexing and Codex learning with synthetic transcripts.
2. Separate manual and background consent. Move learning orchestration to the service. Save pending decisions and private attempt receipts. Make episode processing depend on durable outcomes.
3. Add reviewed historical repository binding, source provenance and removal, and one preference review lifecycle. Migrate existing environment state. Do not discard records, prior revisions, or legacy recovery artifacts.
4. Publish short native rules and full skills together. Repair Claude and Codex destinations and hook commands. Simplify first-run status. Verify ownership, private repository output, manual edits, conflict rollback, and undo.
5. Repair evaluation scoring and resampling, recompute public aggregates, and update the README and guides. Raise the TypeScript limit to 300 lines. Keep the no-comments rule. Repair design-record numbering and long lines in touched files.

## Finding disposition

| Finding or recommendation                                                                                                                          | Decision                                                                                                                  |
| -------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| Disabled indexed sources reach learning, and Codex prompts disappear                                                                               | Fix at authorized evidence selection and provider normalization.                                                          |
| Historical repository rules remain unresolved                                                                                                      | Add reviewed historical binding. Keep unknown identity isolated.                                                          |
| Declined proposals disappear, and onboarding couples manual and background learning                                                                | Save the decision. Split the consent controls.                                                                            |
| Generic background `failed` and opaque no-change                                                                                                   | Add durable outcome receipts and actionable reasons.                                                                      |
| Claude skill reads denied, repeated routing, absolute repository paths, and a bare hook command                                                    | Fix provider delivery and publication ownership.                                                                          |
| Generic skills lower four point estimates, and large baseline reads                                                                                | Make generic skills optional and remove unconditional reads. Do not infer a causal harm from the existing mixed arm.      |
| English steering filter, missing prerequisites, minified error output, and stale profile terminology                                               | Fix eligibility, diagnostics, and user-facing copy.                                                                       |
| Preference replacement, retirement, source removal, and repeated corrections are hard to manage                                                    | Put them in one reviewed lifecycle with revisions and undo.                                                               |
| Unknown verdicts, flattened bootstrap, fragile reply checks, and a misleading README baseline                                                      | Fix the report and recompute it before you use numerical claims.                                                          |
| Task reuse, one user and repository, key from the same learning sample, mixed product revisions, automatic approval, and learning-model dependence | Disclose historical limits. Add a held-out Claude and Codex study that has separate authorization.                        |
| Require a live probe for every approved rule or promise perfect compliance                                                                         | Do not promise compliance. Provide an on-demand bounded probe. Keep publication, loading, and behavior evidence separate. |
| Remove `run`, MCP, and subagents to reduce scope                                                                                                   | Keep them as advanced features and keep them out of first use.                                                            |
| Treat source line count as an architecture defect                                                                                                  | Reject line count as a quality metric. Refactor the confirmed ownership seams and raise the file limit to 300.            |
| Duplicate design numbers and very long lines                                                                                                       | Repair affected docs and touched code without a repository-wide formatting rewrite.                                       |

## Consequences

The change spans persistence, publication, native integrations, setup, and evaluation. Existing environment files, legacy profiles, manual instruction edits, user skills, and revision history must remain readable and reversible. Source removal can require review when one artifact contains guidance from several sources. Native instruction budgets stay bounded. Overflow produces a pending reason. It does not truncate or silently drop a rule.

The Cursor and Antigravity support claims remain. Their provider paths and paid evaluations are outside this implementation round. The existing `run`, MCP, and subagent interfaces remain advanced capabilities. This design justifies no new dependency.

## Verification

Repeated-correction tracking uses the durable `correction` assessments of the learner that attach to existing rules. It does not use every reinforcement or user message. Successful publication dispositions carry an optional publication time. Only later evidence against the current published fingerprint creates a private review signal. The signal stores an evidence hash, rule key, fingerprint, source, and time. Retries deduplicate it. Old dispositions without publication times stay unclassified until Shadowclone republishes them. Counts are review prompts. They are not proof that an agent ignored guidance.

`learning probe` accepts a rule key, Claude Code or Codex, a synthetic task, and an exact expected response. The explicit `--yes` flag authorizes one model call with a 60-second deadline. The probe does these steps:

1. Validate the current owned native instructions and the relevant skill fingerprints.
2. Copy their redacted contents into separate temporary home and workspace directories.
3. Use the native evaluation runner with read access and hooks disabled.

It tests the frozen native guidance. It does not test arbitrary personal files or hook execution. Repository rules need an explicit local integration. Then Shadowclone can freeze their installed native instructions without fabricating hook delivery. Receipts store hashes, provider metadata, permission-denial counts, and pass/fail/error. They do not store prompts or responses. This first isolated probe uses the existing macOS sandbox. Unsupported systems fail before a call. Live hook and package qualification stay separate checks.

Build and test with Bun 1.4.2, which matches the packaged runtime dependency. Declare that version in `packageManager`. The `setup-bun` action of CI reads it before installation. Direct `bun test` and the runtime that package scripts select must use the same bundler. Bun 1.3.3 fails to resolve valid imports in the relocated-package fixture. Linux CI installs both `bubblewrap` and `socat` before it runs the tests. This keeps the Claude sandbox prerequisite checks.

Run focused synthetic contract and regression tests during each stage. For each new regression test, do these steps:

1. Invert the smallest enforcing change.
2. Confirm that the assertion fails.
3. Restore the change.
4. Confirm that the assertion passes.

Before handoff, run `bun run check`, `bun test src/skills`, and `bun run cli --help`. Validate a relocated package and a fresh private installation.

Use at most three short authenticated sessions on each of Claude Code and Codex. Use synthetic prompts and a disposable repository. Verify setup, one approved preference, native delivery in a fresh session, and an on-demand behavior probe. Keep personal transcripts, private receipts, and identifying paths outside the checkout. Report any provider or operating-system limitation. Do not describe untested behavior as verified. Show the completed diff for review before you commit or push.

## Implemented scope and qualification

### Evolution through completed work

The next increment extends maintained skills into task execution inside an existing Claude Code or Codex session. The optional `shadowclone-work` starter skill composes installed guidance. A local task service records acceptance criteria, repository requirements, selected guidance, delegation acknowledgments, verification, independent review, and the requested finish line. Loading guidance is not the same as following it. Execution records never become learning input. Explicit corrections use the existing preference service.

Implement in this order:

1. The task contract and private persistence.
2. Snapshot-bound verification.
3. Ownership and recovery.
4. Explicit action grants and GitHub maintenance.
5. CLI, MCP, and local browser presentation.

Reuse the existing harness, skill delivery, sandbox, remote helpers, and storage primitives. Keep the headless runner and legacy profiles compatible. Version task records independently from existing receipts. Store records and guidance under private run storage, outside the checkout.

Task start reads the current repository instructions and the applicable maintained guidance. It freezes the required gate and verification recipes. It records the Git head and the fingerprints of tracked and untracked changes. A worker cannot remove repository requirements. Verification runs bounded recipes in the existing credential-free sandbox. It records incomplete prerequisites honestly. Substantive work needs an independent review. A changed workspace, guidance snapshot, or grant invalidates readiness. A failed check permits one repair. A further failure blocks the task.

Native sessions own execution. One coordinator reserves each worktree and each file scope. Up to two independent workers can run, but only after explicit workspace and guidance delivery acknowledgments. Unknown host capabilities use serial execution. Durable checkpoints support pause, cancel, and resume. They cause no implicit retries and no deletion of work. Recovery requires that the prior session has stopped. Cleanup never removes unfinished or unpushed worktrees.

Repository grants are explicit decisions that the user makes through the local CLI. They are separate from learned preferences and from the per-run approvals of the legacy runner. Grants cover commit, push, PR creation, reply, and merge. A user can revoke them. Each grant applies only where the task's requested actions and managed policy also allow it. Task helpers verify current evidence before Git writes. They bind PR maintenance to the recorded repository and branch. They never force push. They use exact-head merge checks. Remote operations record intent before execution. An uncertain interrupted operation needs reconciliation, not a blind retry. Maintenance works only inside an active session.

Qualification uses synthetic fixtures and real local Git, CLI, MCP, and sandbox runs. Authenticated host runs, paid evaluation, publication, and the external adopter pilot need separate authorization. Freeze evaluation tasks before you measure preference coverage. Collect accepted changes, review time, corrections, interventions, regressions, and cost. Do not import execution output into learning. Report unqualified host behavior explicitly.

Cancellation keeps ownership until verification has stopped, including cleanup. Frozen guidance records repository instruction paths relative to the worktree. Verification checks for added, removed, and changed instructions in the actual checkout of each worker. A worker cannot reuse a coordinator snapshot when its repository requirements differ.

The implementation adds:

- The opt-in workflow skill.
- Shared CLI and MCP task operations.
- Private versioned records.
- Sandboxed verification recipes.
- Attributed review.
- Bounded worktree ownership.
- Interruption recovery.
- Repository action grants.
- GitHub action journals and reconciliation.
- Browser progress.
- Matched outcome reporting.

Existing skill installation and the headless runner keep their interfaces. New task records do not change legacy receipt formats. They do not give existing repositories new permissions.

Qualification tested real local Git fixtures, stdio MCP initialization and task requests, and the recorded task view of the browser. It also tested the protections of the macOS verification sandbox against Git metadata writes, credential reads, external writes, and networking. A read-only GitHub CLI check confirmed the response shapes and the fallback for missing required checks. Remote write paths use synthetic contract tests. Regression checks showed a failure when someone removed snapshot binding or task action restrictions. They reproduced instruction drift and cancellation races before the fixes.

No real Claude Code or Codex agent run, live GitHub write, matched held-out study, or adopter pilot has qualified the engineering workflow yet. These stay release gates. The native preference-delivery qualification below came earlier. It covers learning and delivery, not this new task lifecycle. The local checks show no superiority in throughput or security.

### Plugin bootstrap qualification

The packaged setup skill checks the installed CLI version before it reads setup state. A bundled Node helper runs only `shadowclone --version`, with bounded output and a timeout. It requires stable CLI version 0.0.13 or newer. A missing or older installation prompts a decision to install or upgrade. After the user approves, the skill installs the public package without elevated privileges and repeats the compatibility check. A compatible existing installation keeps its consent settings. If the public package is still too old, setup stops before initialization and explains the action to take. Setup also stops in this way when a different executable shadows the installation.

Qualify the release candidate in a disposable installation prefix and agent home. Use these steps:

1. Install the plugin through the marketplace flow of Claude.
2. Install the packaged candidate through npm.
3. Test explicit consent.
4. Load and apply the browser build.
5. Reconnect the configured stdio MCP server.
6. In fresh Claude Code and Codex sessions, test both global and repository preferences.
7. Undo the recorded change and refresh integrations.
8. In a second fresh session, confirm the prior behavior.

Use synthetic guidance and tasks, and at most four model calls. Keep private qualification output outside the checkout. This verifies the candidate package. The registry upgrade path depends on the publication of that candidate. The follow-up PR uses a conventional `fix:` title, so its squash merge is releasable.

The implementation includes:

- Current source authorization.
- Codex user-message extraction.
- Separate manual and background consent.
- Durable proposals and attempt receipts.
- Reviewed historical repository association.
- Source provenance.
- Reversible preference edits.
- Review signals for later corrections.
- An on-demand native response probe.

The CLI and workers use learning application services. Legacy profile and library entry points stay as compatibility paths. Publication keeps ownership, edited native destinations, original resources, and revision recovery. Short rules are inline. Workflow skills use native names. Generic starter workflows are optional. Hooks use an owned launcher that does not depend on `PATH`. Source removal records the pending rejection and the environment retirement together, so undo restores both.

Synthetic contract tests cover each supported learning provider. The tests run from capture through declined review, failed publication, retry, and successful publication. They cover both native guidance formats. Tests run the relocated package against a fresh private home. This includes a launcher invocation with no Shadowclone executable on `PATH`. Three short synthetic sessions for each agent qualified live native delivery and the bounded probe. Both final probes matched their expected response with no permission denials. The record of a probe pass is independent of skill reads and hook observation.

The project recomputed the published preference-study tables from private receipts with `session-bootstrap-2`. It made no paid reruns. The corrected intervals show no incremental advantage over existing user skills. The receipts omitted the product commit of each historical session, so no one can reconstruct those commits. Held-out users, repositories, future tasks, alternative learning models, and intervention measurements stay a separate study. The first isolated probe needs macOS and text skill resources. Cursor and Antigravity qualification stays outside this round.

### Constellation spacing and scale

The fixed canvas layout compresses skill rows as the library grows. Replace proportional row spacing with a world layout. The layout reserves 88 pixels per skill and separate columns for sibling branches. Pan and zoom show the larger world without reducing the distance between nodes. Fit calculates the actual graph bounds. Reset restores a readable scale and centers the view on the root.

The collapsed overview wraps categories into rows of at most four hubs. Then twelve categories stay visible. They do not extend off-screen in one row. Expanding a branch uses the larger world layout. Search centers its matching skill, also after category focus. List filtering updates independently of the dimensions of the hidden map.

Render the existing Shadowclone mark inside the root circle. Use the existing SVG icon vocabulary for category hubs. Wrap long labels within their column, so they do not overlap neighboring branches. Libraries with more than 40 leaves begin with collapsed categories. Users expand a branch to see its subcategories and skills. Search reveals the matching ancestor branches. The list view keeps access to every skill. Test dispersed libraries and single-category libraries of up to 500 skills. Cover spacing, expansion, search, and viewport transforms.

The live 500-skill fixture reached the 500-file limit of discovery before the renderer ran. Bound discovery at 2,000 distinct physical files. Keep the existing 8 MB byte limit, 48 KB per-skill limit, path-depth limit, and consented roots. Count a canonical file once when roots overlap. This permits a 500-skill library with native copies. Bound each category branch to ten children, recursively. Then a single large category also opens in manageable groups. The list and search traverse every nesting level.

The packaged 500-skill build response took about eight seconds under local load. This is close to the default ten-second HTTP idle timeout of Bun. Set the idle timeout of the loopback editor to ninety seconds. This also covers its bounded sixty-second model action. Show loading and retry states while the catalog request runs. Then a slow or interrupted response never looks like an empty installed library.

### Follow-up qualification results

A disposable macOS installation tested these steps:

- The marketplace installation of Claude Code.
- The npm installation of the packaged 0.0.13 candidate.
- Explicit initialization choices.
- Browser review and application.
- Undo.
- MCP reconnection.

Initialization with session learning and background learning declined kept those decisions. With the published 0.0.12 CLI installed, the setup helper reported `outdated`. After the upgrade to the candidate, it reported `ready` and did not change the consent configuration. The plugin health check of Claude Code reported `Connected`. Two fresh stdio connections completed initialization, tool discovery, and a context request.

Four authenticated sessions checked the native delivery and removal of independently authored synthetic global and repository preferences. Each active session returned both installed preference values. The test then undid the four preference decision and publication revisions and refreshed native integrations. After that, each fresh session returned both fallback values. All four calls finished without permission denials.

| Agent       | CLI     | Model             | Global and repository delivery | Both preferences after undo |
| ----------- | ------- | ----------------- | ------------------------------ | --------------------------- |
| Claude Code | 2.1.284 | claude-sonnet-5-5 | Passed                         | Restored prior behavior     |
| Codex       | 0.159.0 | gpt-6-sol         | Passed                         | Restored prior behavior     |

The publisher used synthetic model responses. The four real calls tested fresh native sessions, and the qualification runner disabled hooks. The package and plugin checks tested the installed CLI separately. This qualification does not rerun the preference study. It does not measure an agent that conducts the setup conversation. Candidate artifacts, agent output, and receipts stay outside the public checkout.

Browser qualification loaded 519 skills, including 500 synthetic skills in one category. The collapsed overview showed every category. Expansion showed bounded subgroups. Search revealed a deeply nested skill after the user focused a different branch. The list kept all 519 entries. A final review of a normal library applied a build and then restored it with undo. The registry setup path becomes available when the project publishes the next release. Creating the follow-up PR alone does not publish the CLI.
