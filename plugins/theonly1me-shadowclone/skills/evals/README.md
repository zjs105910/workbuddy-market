# Evaluations

Maintainers run these suites from a source checkout. The published CLI does not contain them. The [results](../evals.md) compare five setups on four models.

## Suites

- **Preference benchmark** (`bun run eval --protocol preference-respect-v3`): how well learning keeps your rules and agents receive them. Earlier protocols `preference-respect-v1`, `preference-respect-v2`, and `preference-study-v1` still run.
- **Routing experiment** (the same command with `--experiment routing`): whether native routing changes skill selection and compliance.
- **Work suite** (`bun run eval:work`): whether `shadowclone-work` takes a case to a ready pull request.
- **Workflow outcomes** (`bun run eval --protocol workflow-outcomes-v1`): frozen tasks under existing skills, current Shadowclone, and an evolved workflow.
- **Pull request review** ([`pr-review/README.md`](pr-review/README.md)): the precision of reviewers on merged pull requests.
- **No-comments** ([`no-comments/README.md`](no-comments/README.md)): whether agents write more readable code without comments.

## Rules for paid runs

1. Review, preparation, and offline validation make no authenticated call. An authenticated phase (`learn` or `run`) needs a newly approved scope. Run the `approve-*` phase first.
2. The scope names the host, model, effort, and call ceiling. Pass `--yes` only for that exact scope. An earlier approval never covers a new scope.
3. Keep suites, keys, agent homes, and receipts in a new private directory outside every repository. The tools refuse a folder inside a repository.
4. Keep held-out cases outside every checkout. Only their hashes and family coverage are public.

## Preference benchmark

Use the source checkout and its pinned Bun. Every output path is a new private directory under `$PRIVATE_ROOT`.

### The fixed contract

The benchmark has 24 synthetic tasks in eight preference families. They are comments, types, API conventions, Git authorization, answer length, test-first behavior, pull request structure, and scope and lifecycle. Each family has 2 development cases, 1 held-out case, and a headline weight of 12.5%. The five setups are:

- **Agent alone:** shared repository requirements.
- **Existing user skills:** an unchanged handwritten code-style skill.
- **Existing skills + Shadowclone routing:** the same library with production initialization and native startup guidance.
- **Existing skills + handwritten preferences:** the routed library plus independently handwritten intended guidance.
- **Existing skills + Shadowclone learning:** the routed library plus the actual learning output.

Handwritten and learned guidance share a delivery path and add no answers to task prompts. Saved receipts call them `told` and `deep`. Their gap measures how closely learning follows the intended guidance, and the gap between learning and routing measures its effect.

The authored inputs are the [public cases](fixed/reusable/cases/), the [target specification](fixed/reusable/oracle.ts), the [manual guidance](fixed/reusable/guidance.ts), the [correction corpus](fixed/reusable/corpus.ts), and the [held-out manifest](fixed/reusable/heldout-manifest.json). The corpus has repeated examples, conditional defaults, a one-task waiver, a replacement of an older instruction, insufficient evidence, and tool-result decoys. The decoys must stay out of learning text.

The eight held-out cases live in a private bundle. Back it up on its own, because hashes cannot rebuild it, and never give it to an optimizer. Humans inspect it before the freeze, and candidates read its prompts only during qualification.

The [routing experiment](fixed/reusable/routing.ts) compares the same 20 manual skills with and without routing on 12 public cases. Selection needs the relevant skill read and no unrelated library read. Compliance checks the generated code. It uses no learning calls.

### Phases

Run each phase as `bun run eval --protocol preference-respect-v3 --phase <phase> <flags>`.

1. **Review.** `review --bundle-file "$PRIVATE_ROOT/heldout/bundle.json" --review-file "$PRIVATE_ROOT/review.json"` writes the private review artifact with the expected verdict, check kinds, and calibration fingerprint of each case. Read it first.
2. **Approve the review.** `approve-review --review-file "$PRIVATE_ROOT/review.json" --fingerprint "$REVIEW_FINGERPRINT"` authorizes no model call.
3. **Prepare.** `prepare-environments --bundle-file ... --review-file ... --model "$LEARNER_MODEL" --effort medium --maximum-calls 16 --output-directory "$PRIVATE_ROOT/environments"` pins one Codex learner, its CLI version, model, effort, source snapshot, runtime, graders, corpus, and manual guidance. It creates three independent learning homes with the same guidance. Each preparation allows at most 16 calls, a two-minute call timeout, and a 20-minute deadline. A read-only check first confirms that all 22 assistant examples and user corrections survive redaction. That keeps 11 paired steering episodes and drops the tool-output decoy.
4. **Optional preflight.** Run `prepare --experiment learning --run-phase preflight` from `preparation.json`, without an environments file. It uses the 16 public cases, the bare and told setups, one repetition, no learning call, and no held-out prompt. Approve this scope on its own. It reports baseline saturation and unmet told checks. Never drop checks because of its results.
5. **Learn.** `approve-learning --preparation-file "$PRIVATE_ROOT/environments/preparation.json" --fingerprint "$PREPARATION_FINGERPRINT"` creates the exact scope. Then `learn --preparation-file ... --scope-file "$PRIVATE_ROOT/environments/learning-scope.json" --yes` runs it with the production learning paths on synthetic instructions only, in sandboxes with no tools and no memory. The run keeps published text, pending proposals, absent expected rules, and suspected unsupported guidance. Never replace missing or pending guidance with the told answers.
6. **Review learning.** Copy the `learning-assessment-draft.json` that the run wrote. Record the missing rule ids and the unsupported published keys, with reasons, and set its decision to `reviewed`. Then run `review-learning --environments-file ... --assessment-file ...`. Qualification needs all three assessments.
7. **Freeze each cohort.** `prepare --preparation-file ... --environments-file "$PRIVATE_ROOT/environments/environments.json" --experiment learning --run-phase development --engine codex --model "$SCORED_MODEL" --effort medium --output-directory "$PRIVATE_ROOT/development"`. Use `--engine claude-code` for Claude. Use `--run-phase qualification` (all 24 cases) only after the preflight and case review. For the routing experiment, use `--experiment routing`, omit `--environments-file`, and use a new output directory. A change of agent or model needs its own qualification.
8. **Validate, approve, run, report.** Run `validate`, `approve-run`, `run`, and `report` with `--suite-file "$PRIVATE_ROOT/development/suite.json"`. Add `--fingerprint "$SUITE_FINGERPRINT"` to `approve-run`, and `--scope-file "$PRIVATE_ROOT/development/run-scope.json" --yes` to `run`.

An interrupted preparation gets no new budget without approval. A model or infrastructure failure blocks qualification. Keep the evidence and approve a fresh cohort. To reuse completed learning for a new cohort, build fresh environments with `prepare-environments`, then run `reuse-learning --source-file .../learning-source.json --preparation-file .../preparation.json`. Reuse makes no model call. It needs a match on the sealed learning code, fixtures, corpus, runtime inputs, initial guidance, learner model, effort, CLI, and call ledgers. Any other change needs a fresh authorized preparation.

| Experiment             | Sessions per model | Planned turns | Reserved retry turns | Candidate ceiling | Shared preparation ceiling |
| ---------------------- | -----------------: | ------------: | -------------------: | ----------------: | -------------------------: |
| Bare/told preflight    |                 32 |            32 |                   32 |                64 |                          0 |
| Learning development   |                240 |           240 |                  240 |               480 |                         48 |
| Learning qualification |                360 |           360 |                  360 |               720 |                         48 |
| Routing                |                 72 |            72 |                   72 |               144 |                          0 |

Qualification plus routing across four models has a ceiling of 3,504 calls. Most runs use fewer, because the ceiling includes one replacement for each cell.

Validation checks grader outputs, acceptance failures, and passing reference implementations, and runs a real read-only mount and an answer-access probe, with no authenticated call. A failed validation blocks the run. Run the native macOS sandbox checks outside any enclosing agent sandbox. They do not qualify the Claude sandbox. The run is serial and reserves every native invocation first. A resume checks the fingerprints again and keeps completed, unfavorable, and interrupted cells.

### Failures and resumes

- One confirmed infrastructure failure allows one replacement in a fresh workspace. Both attempts stay in the receipt and count toward the ceiling.
- A clear provider quota refusal before any agent action creates `provider-pause.json` and stops dispatch. Wait for the reset, then remove the marker and its sidecar.
- An unresolved setup, mount, verification, or cleanup failure creates `infrastructure-hold.json`. Read its evidence before you remove the marker.
- An ordinary model failure is a recorded outcome and authorizes no replacement call.
- Before you remove the `.running` lock of an interrupted process, confirm that it ended.
- A report charges every reservation in the durable ledger. An unattributed reservation or pending dispatch leaves the run incomplete.

### Isolation, scores, and comparison

Each task gets a disposable repository and an isolated agent home. Candidates cannot read grading answers or contact a real remote, and remote actions use a local bare Git origin and recorded offline `gh` calls. Each host needs its own sandbox qualification.

A session score is the share of required preference checks that pass. Average complete repetitions and cases inside each family, then average the eight family scores.

- Answer length counts all whitespace-separated tokens in the final answer, including code and fences. The default allows 80 tokens, and the 250-word override accepts 220 through 280.
- Correctness, safety, unsupported learning, selection, and completion have separate fields. Missing evidence leaves the headline incomplete.
- The 95% intervals resample the three whole repetition and preparation groups, with the task mix fixed. Three groups give coarse intervals, and cohorts that share preparations correlate.
- To compare two product branches, run `--phase compare --baseline-file ... --candidate-file ...`. Cases, inputs, learner configuration, agent versions, models, efforts, runtime, and budgets must match.

Reuse this benchmark version for product changes. Change the version when the contract changes, and keep older records.

## Work suite

`bun run eval:work` runs `claude plugin eval` on synthetic pull request histories, each with a local bare remote and a stand-in for `gh`. A grader checks the code checks on the final head and that the pull request is ready and not merged. It also checks the thread replies, silence on the pull request, and history rewrites outside `gh stack`. See [design record 030](../docs/design/030-shadowclone-work-eval.md).

## Reading the results

Public reports hold aggregate scores and limits, never prompts, transcripts, credentials, identifying paths, or generated code. Before you publish qualification results, inspect ambiguous verdicts and report saturation without removing checks. Publish all setup and family scores, the preparation outcomes, the limits, and the phase.
