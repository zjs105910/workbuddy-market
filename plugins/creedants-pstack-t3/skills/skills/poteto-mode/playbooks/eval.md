### Eval

**You own the experiment design. Plan, blind, run, synthesize.**

**Non-negotiables for blinding:**

- No `eval`, `test`, `judge`, `experiment`, `rubric`, `score`, `compare`, `benchmark`, `candidate`, or `arena` in any directory, file, or prompt the candidate sees.
- The candidate prompt looks like an organic user request. State the goal, not the meta.
- No chain-eliciting cues. Don't ask the candidate to list which skills, principles, or files they applied. Ask for design notes generally and grade chain-following from code shape, not self-report.
- Sanitize directory and slug names. Use project-shaped names a user might pick. The `delegate_task` `title` and `clientRequestId` count as names the candidate may see, so sanitize them too.
- Don't tell the candidate other candidates exist.
- The judge can know it's judging but sees outputs by sanitized label only, never by model name.
- Comparing two variants: one judge scores both sets in a single pass on one scale, blind to which set each came from.

**Steps:**

1. **Frame.** State what variant is under test and what behavior counts as success. Write the rubric (3-6 concrete criteria) for the judge only. Hold it back from candidates.
2. **Set up sanitized environments.** Per-candidate working dir with the variant in place. Plant any context an organic task would have: a project skeleton, the skills the candidate would naturally read.
3. **Author one organic prompt.** What a user would type. No leakage of what's being measured.
4. **Spawn N parallel candidates** on different models per the **arena** skill's Phase B. Each candidate is a fresh child task, one `delegate_task` call with `mode: "async"` and a resolved `target` per [the runtime's Delegation section](../../pstack-runtime/SKILL.md#delegation), all in one message. Never reuse a candidate's thread for another arm or a rerun. Each works in its own sanitized dir. Same prompt to each. Retain each `taskId` and `childThreadId` against its sanitized label, out of the judge's sight.
5. **Spawn one blinded judge** on a different model family per the **arena** skill's Phase C, as a fresh child task whose `target` names a model family no candidate used. Judge sees outputs by sanitized label and the rubric, never a model name.
6. **Verify the chain from threads, not self-report.** Each candidate's child task is a T3 thread. Read it with `t3_thread_read` on its `childThreadId` with `view: "activity"`, paging with `afterPosition`, per [the runtime's History section](../../pstack-runtime/SKILL.md#history). Look at which files each candidate actually opened. Grade chain-following from the files it really read plus the shape of the code, never from the candidate's own claims.
7. **Read every candidate output yourself** end to end. Compare to the judge's verdict. Disagreement means a model is biased or the rubric is ambiguous. Synthesize.

**Reply:** variant under test, rubric, per-candidate notes, judge's verdict, your synthesis, and a recommendation for whether to promote the variant.
