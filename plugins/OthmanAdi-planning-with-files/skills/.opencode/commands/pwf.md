---
description: Start planning-with-files (task_plan.md, findings.md, progress.md); flags --gated, --autonomous, --template analytics, then an optional plan name
---
Start the planning-with-files workflow for this project.

Arguments given: "$ARGUMENTS"

1. Call the `pwf_init` tool. Map the arguments: `--gated` sets mode "gated", `--autonomous` sets mode "autonomous", `--template analytics` sets template "analytics"; every remaining word forms the plan name. A name creates an isolated `.planning/YYYY-MM-DD-<slug>/` plan and makes it the active plan; no name uses the project root.
2. Read the created `task_plan.md`, `findings.md` and `progress.md` from the directory the tool reports, then fill in the goal, the next step and the phases for the task at hand before any other work.
3. Follow the planning-with-files skill from then on: update `progress.md` after every action, log errors in the plan, and mark phases complete as they finish.
