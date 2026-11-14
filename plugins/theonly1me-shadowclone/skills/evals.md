# Evaluation results

This evaluation tests whether agents follow engineering preferences. It uses 24 fixed tasks, and every setup ran all tasks three times on each model, which makes 72 sessions for each setup and model. All planned tasks stay in the comparison, and the tables use the final authorized attempts.

## Preference adherence

Each task checks one preference family. The score averages repetitions and tasks inside each family, then weights the eight families equally. It does not measure task success or code quality.

| Setup                                     | GPT 6.1 Sol | GPT 6 Luna | Claude Sonnet 5.5 | Claude Opus 5.5 |
| ----------------------------------------- | ----------: | ---------: | ----------------: | --------------: |
| Agent alone                               |       77.3% |      59.0% |             56.5% |           53.2% |
| Existing user skills                      |       85.2% |      80.6% |             76.4% |           73.6% |
| Existing skills + Shadowclone routing     |       86.1% |      72.7% |             76.9% |           75.9% |
| Existing skills + handwritten preferences |       92.4% |      81.2% |             91.7% |           86.1% |
| Existing skills + Shadowclone learning    |       89.4% |      83.3% |             90.0% |           82.9% |

Learning beats existing user skills on all four models. Handwritten preferences score higher than learned ones on GPT 6.1 Sol, Sonnet, and Opus, but not on GPT 6 Luna. Learning delivery and model behavior affect this comparison.

## What each setup means

The [fixed contract](evals/README.md#the-fixed-contract) defines the five setups. Saved receipts name them `bare`, `skills`, `routing`, `told`, and `deep`.

## Per-preference results

Each family has three tasks and three repetitions. Columns follow the rows of the first table. Answer length counts for at most 12.5% of the headline.

### GPT 6.1 Sol

| Preference          |  Alone | Skills | Routing | Handwritten | Learning |
| ------------------- | -----: | -----: | ------: | ----------: | -------: |
| Comments            | 100.0% | 100.0% |  100.0% |      100.0% |   100.0% |
| Type safety         | 100.0% | 100.0% |  100.0% |      100.0% |   100.0% |
| API conventions     |  33.3% | 100.0% |  100.0% |      100.0% |   100.0% |
| Git authorization   |  51.9% |  48.1% |   55.6% |      100.0% |    81.5% |
| Answer length       |  66.7% |  66.7% |   66.7% |       66.7% |    66.7% |
| Test-first behavior | 100.0% | 100.0% |  100.0% |      100.0% |   100.0% |
| PR structure        |  66.7% |  66.7% |   66.7% |       72.2% |    66.7% |
| Scope and lifecycle | 100.0% | 100.0% |  100.0% |      100.0% |   100.0% |

### GPT 6 Luna

| Preference          |  Alone | Skills | Routing | Handwritten | Learning |
| ------------------- | -----: | -----: | ------: | ----------: | -------: |
| Comments            | 100.0% | 100.0% |  100.0% |      100.0% |   100.0% |
| Type safety         |  44.4% |  88.9% |  100.0% |       88.9% |   100.0% |
| API conventions     |  33.3% | 100.0% |   88.9% |      100.0% |    88.9% |
| Git authorization   |  77.8% |  77.8% |   70.4% |      100.0% |    88.9% |
| Answer length       |  44.4% |  66.7% |   44.4% |       44.4% |    66.7% |
| Test-first behavior |  33.3% |  55.6% |   33.3% |       33.3% |    44.4% |
| PR structure        |  66.7% |  66.7% |   66.7% |       83.3% |    77.8% |
| Scope and lifecycle |  72.2% |  88.9% |   77.8% |      100.0% |   100.0% |

### Claude Sonnet 5.5

| Preference          |  Alone | Skills | Routing | Handwritten | Learning |
| ------------------- | -----: | -----: | ------: | ----------: | -------: |
| Comments            | 100.0% | 100.0% |  100.0% |      100.0% |   100.0% |
| Type safety         |   0.0% | 100.0% |  100.0% |      100.0% |    88.9% |
| API conventions     |  33.3% | 100.0% |  100.0% |      100.0% |   100.0% |
| Git authorization   |  55.6% |  55.6% |   55.6% |      100.0% |    85.2% |
| Answer length       |   0.0% |   0.0% |    0.0% |       55.6% |    77.8% |
| Test-first behavior | 100.0% | 100.0% |  100.0% |      100.0% |   100.0% |
| PR structure        |  66.7% |  66.7% |   66.7% |       77.8% |    72.2% |
| Scope and lifecycle |  96.3% |  88.9% |   92.6% |      100.0% |    96.3% |

### Claude Opus 5.5

| Preference          |  Alone | Skills | Routing | Handwritten | Learning |
| ------------------- | -----: | -----: | ------: | ----------: | -------: |
| Comments            |  77.8% | 100.0% |  100.0% |      100.0% |   100.0% |
| Type safety         |  22.2% | 100.0% |  100.0% |      100.0% |   100.0% |
| API conventions     |  33.3% | 100.0% |  100.0% |      100.0% |   100.0% |
| Git authorization   |  48.1% |  44.4% |   51.9% |      100.0% |    81.5% |
| Answer length       |   0.0% |   0.0% |    0.0% |       22.2% |    22.2% |
| Test-first behavior | 100.0% | 100.0% |  100.0% |      100.0% |   100.0% |
| PR structure        |  66.7% |  66.7% |   66.7% |       66.7% |    66.7% |
| Scope and lifecycle |  77.8% |  77.8% |   88.9% |      100.0% |    92.6% |

## Matched comparisons

Differences are in percentage points. The 95% bootstrap intervals resample the three matched groups of repetition and learning preparation, with the task mix fixed. Three groups give coarse intervals. Models share preparations, so do not pool them.

| Model             | Learning over routing | 95% interval  | Learning over handwritten preferences | 95% interval |
| ----------------- | --------------------: | ------------- | ------------------------------------: | ------------ |
| GPT 6.1 Sol       |                  +3.2 | 0.0 to +5.1   |                                  -3.0 | -6.9 to -0.7 |
| GPT 6 Luna        |                 +10.6 | +2.1 to +16.2 |                                  +2.1 | 0.0 to +3.5  |
| Claude Sonnet 5.5 |                 +13.2 | +8.3 to +15.7 |                                  -1.6 | -2.8 to -0.7 |
| Claude Opus 5.5   |                  +6.9 | +1.4 to +10.6 |                                  -3.2 | -5.6 to -1.4 |

## Separate routing comparison

A second experiment uses 20 synthetic skills, twelve tasks, and three repetitions for each setup. It scores selection and compliance separately.

| Model             | Existing skills | + Routing |
| ----------------- | --------------: | --------: |
| GPT 6.1 Sol       |          100.0% |    100.0% |
| GPT 6 Luna        |          100.0% |     97.2% |
| Claude Sonnet 5.5 |          100.0% |    100.0% |
| Claude Opus 5.5   |          100.0% |    100.0% |

Both Claude models selected the expected skills in every session. Codex read tracking missed some reads, and the original verdicts stay. Task names match skill names, and the routing is generic startup guidance, so the experiment says nothing for or against explicit production routes.

## Correctness, safety, and learning

These correctness counts cover all 72 sessions for each setup, with the original acceptance verdicts. API and advice acceptance limits affect how to read them. Routing correctness is not compared, because its acceptance assumes a fixed module location.

| Setup       | GPT 6.1 Sol | GPT 6 Luna | Claude Sonnet 5.5 | Claude Opus 5.5 |
| ----------- | ----------: | ---------: | ----------------: | --------------: |
| Alone       |       72/72 |      69/72 |             71/72 |           72/72 |
| Skills      |       72/72 |      72/72 |             68/72 |           69/72 |
| Routing     |       71/72 |      70/72 |             69/72 |           69/72 |
| Handwritten |       70/72 |      72/72 |             69/72 |           69/72 |
| Learning    |       70/72 |      72/72 |             68/72 |           69/72 |

All planned sessions completed, and protected manual guidance stayed unchanged in every final session. No fixture action reached a real remote.

Three independent learning preparations used GPT 6.1 Sol at medium effort. One published four intended rules and left Git guidance pending, and two published five. All three published partial pull request guidance. A bounded agent assessment found no unsupported guidance. Nobody added the missing rules.

## Method and measurement limits

The study ran on 2026-10-03: 1,440 five-setup sessions and 288 routing sessions.

- GPT 6.1 Sol: Codex 0.159.0, medium effort.
- GPT 6 Luna: Codex 0.159.0, high effort.
- Claude Sonnet 5.5: Claude Code 2.1.287, high effort.
- Claude Opus 5.5: Claude Code 2.1.287, medium effort.

The declared runtime is Bun 1.4.2 and TypeScript 5.9.3, but acceptance logs show both Bun 1.3.3 and 1.4.2. Each cohort has one fixed effort, so the study does not isolate model size or effort. An agent audit of twenty saved sessions changed no score and is not an independent human review. API acceptance assumes fixed option names, and an advice keyword check can reject an equivalent explanation. These limits prevent a clean claim about correctness or general engineering quality.

Claude runs after a quota reset used authorized manual retries. The study removed or rescored no failure in silence. The design follows [Automating eval design and hillclimbing with Claude](https://claude.dev/blog/automating-eval-design-and-hillclimbing/). No autonomous hillclimbing ran. Production representativeness, independent expert agreement, and effort scaling stay unproven.

See the [evaluations guide](evals/README.md), the [pull request review](evals/pr-review/README.md) evaluation, and the [no-comments](evals/no-comments/README.md) evaluation. These results support a bounded claim about preference delivery on synthetic tasks, not production throughput, security superiority, or a universal routing benefit.
