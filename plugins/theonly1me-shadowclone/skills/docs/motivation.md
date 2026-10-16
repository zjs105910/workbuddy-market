# Why I built Shadowclone

I want to trust coding agents with large changes in large repositories, and I want the result to follow my engineering standards. These standards cover how much to change at once, how to organize code, and when to plan, test, or stop. Fast code helps only if I control those decisions.

I kept repeating the same preferences. The agent could often do the task, but I had to explain how I wanted it done. Instruction files and skills helped, but keeping them current was the hard part. Some described preferences that I had changed. Others missed guidance that came up only when I corrected an agent. Each new tool meant another copy to maintain.

Shadowclone maintains that setup across the agents that I use. It learns from the sessions that I enable, updates the relevant skills, and carries them between agents. Evidence and revisions stay on my machine. The same skills drive a cloud bot on GitHub. The skills and instructions stay as files that I can read and change. A change of agent should not restart that work. I decide what becomes a lasting rule.

## Built entirely with agents

I built Shadowclone without writing code by hand. Agents write code faster than I do. I set the requirements and guardrails and direct the agents to those standards.

I do not call that vibe coding. I care about the architecture, types, module boundaries, and tests, even when an agent writes every line. My responsibility for the result stays the same. The repository has more than 800 source and test files. Inspect it, or ask your coding agent to review it. Ask whether the design is coherent, whether the tests catch real failures, and whether the code follows its own engineering rules. If it looks vibe coded to you, point to the code that says so.

## What matters to me

A correction should improve the next session without turning every interaction into a rule. A temporary exception should stay temporary. A preference from one project should stay in that project unless I make it global on purpose. I want to see why guidance exists and undo a change that I disagree with.

Learning needs evidence. The [evaluations](../evals.md) show that setups differ in how well an agent follows preferences. They use 24 fixed synthetic tasks, so they do not show that maintained skills improve every task or save a set amount of time. A first run also exposed product defects that later runs fixed. Guardrails cannot promise perfect adherence. An honest measurement reports when extra guidance makes no difference or makes an agent worse.

Coding sessions can hold sensitive material. Source access is opt-in, and changes are reversible. Model work uses the agent provider that you select, so local storage does not mean that the analysis stays offline. [Data handling](data-handling.md) explains that boundary.

## Related approaches

Instruction files, skills, and memory stay part of the setup that Shadowclone maintains:

- **Repository instructions** hold explicit project conventions. Keep them current and readable by the chosen agents.
- **Personal skills** hold reusable task workflows. Watch routing, ownership, supporting resources, and conflicting copies.
- **Native memory** carries context between sessions. Watch scope, accuracy, retention, and correction.
- **Transcript analysis** finds repeated steering. It needs consent and evidence that justifies durable guidance.
- **Evaluation** checks behavior under stated guidance. It needs fair baselines and correctness checks.

Well-maintained instructions may already give you what you need. The useful comparison is the effort and quality of keeping that setup current. More guidance can help, change nothing, or cause a conflict.
