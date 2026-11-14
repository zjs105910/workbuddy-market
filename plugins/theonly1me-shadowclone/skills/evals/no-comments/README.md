# No-comments eval

This eval tests whether agents write more readable code when they cannot write comments. Four model settings got the same feature request in a small Python codebase, 20 times each, half with comments banned. Two LLM judges then compared each pair blind, with all comments removed.

## Headline

**Yes, in this test. The judges preferred the comment-free code in 62% of pairs, and a second batch agreed.**

The comment-free code won **62% of 80 pairs** (95% interval 53% to 70%, p = 0.009). The first batch of 40 pairs gave 59% (p = 0.16). The authors committed the rules for a second batch before it ran. It gave 64% on its own (p = 0.027).

| Setting                 | Comments per run when free | Comment-free judged easier to read |
| ----------------------- | -------------------------: | ---------------------------------: |
| Claude Sonnet 5.5, high |                        6.2 |                   69% (51% to 85%) |
| Claude Opus 5.5, medium |                        6.2 |                   75% (59% to 89%) |
| GPT 6 Luna, high        |                        2.0 |                   54% (39% to 69%) |
| GPT 6.1 Sol, medium     |                        1.3 |                   50% (34% to 66%) |

- **The Claude models gained the most.** They comment a lot when allowed. The Codex models rarely comment, so the ban changed little, and 20 pairs each is too few to tell.
- **The ban did not cost correctness.** The models passed 7,995 of 8,000 hidden tests in both conditions. All 80 banned runs obeyed the ban.
- **Code measurements showed little.** Sonnet's comment-free code had a lower maximum complexity (1.7) and a shorter longest function (4.5 lines). Others did not move.

## How it works

1. **The task.** The agent adds usage-based billing and mid-cycle plan changes to `ledger`, a small billing library in [`task/seed_repo`](task/seed_repo). The [prompt](task/prompt_base.md) states 12 rules, so tests can grade the result.
2. **The conditions.** Condition A is silent on comments. Condition B adds one sentence: "Do not write any comments in code. This includes # comments and docstrings."
3. **Clean runs.** Every run starts in a fresh repository copy with no user instructions, skills, or MCP servers. Claude Code and Codex run headless.
4. **Grading.** 50 [hidden tests](graders/hidden_tests) check behavior, and a [counter](graders/comments.py) checks that banned runs wrote no comments. Two judges, Claude Opus 5.5 and GPT 6.1 Sol, compare each pair in both orders with a [rubric](graders/judge/rubric.md).

## Limits

- It is one task in one codebase, graded by models. The lead over a coin flip is 12 points (interval 3 to 20).
- The authors extended the study after the first batch, so the combined p-value is optimistic. The second batch alone is cleaner.
- Per-setting results are descriptive and can be chance.
- The seed code has 3 comments, and the Claude Code prompt tells the model to match nearby comments. Both may push condition A toward more comments.
- Effort differs between settings, so compare A with B inside a setting.

## Run it yourself

You need the signed-in `claude` and `codex` CLIs and Python 3.11 or newer.

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m harness.run_all --repetitions 10 --concurrency 4
.venv/bin/python -m harness.run_all --first-repetition 11 --repetitions 20 --concurrency 4
.venv/bin/python -m graders.judge.run --concurrency 4
.venv/bin/python -m analysis.analyze
```

Before the first run, set `EVAL_LEAK_MARKERS` to distinctive strings from your own instruction files. Then run `python -m harness.isolation_check <setting>` to confirm that none reach a run. [`harness/matrix.json`](harness/matrix.json) holds the four settings.

[shadowclone-no-comments-runs](https://github.com/theonly1me/shadowclone-no-comments-runs) holds the full method, all result tables, 160 runs, and 320 judge verdicts. See its [results page](https://github.com/theonly1me/shadowclone-no-comments-runs/blob/main/RESULTS.md) and [code examples](https://github.com/theonly1me/shadowclone-no-comments-runs/blob/main/EXAMPLES.md).
