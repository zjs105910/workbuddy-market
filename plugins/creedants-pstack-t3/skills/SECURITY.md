# Security policy

pstack-t3 runs agents that execute commands, edit files, and open pull requests. Treat a flaw that lets a skill escape its brief as a security bug.

## Report a vulnerability

Report it privately through [GitHub's private vulnerability reporting](https://github.com/creedants/pstack-t3/security/advisories/new). Do not open a public issue.

Include the skill or script, the provider and model that led the thread, and the steps that reproduce it. You get a reply within seven days.

## In scope

- A skill that runs commands, writes files, pushes, or merges beyond what its playbook allows.
- `scripts/install.py` writing, replacing, or deleting files outside the skill directories it reports.
- Credentials, tokens, or thread contents leaking into commits, logs, or child-task briefs.

## Out of scope

- Bugs in T3 Code itself. Report those to [pingdotgg/t3code](https://github.com/pingdotgg/t3code).
- Bugs in upstream pstack content. Report those to [cursor/plugins](https://github.com/cursor/plugins).
- A model ignoring a skill's instructions with no flaw in the skill.

## Supported versions

Only the latest release and `main` get fixes.
