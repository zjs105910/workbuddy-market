### Authoring or modifying a skill

**You own the skill's voice.**

1. Use the **pstack-author-skill** skill. Skills install per provider. Claude reads `~/.claude/skills`, Codex reads `~/.agents/skills`, Grok reads `~/.grok/skills`, and Cursor reads `~/.cursor/skills`. Install to every provider the user runs. T3's `$` skill picker lists what each provider sees, except Muse's skills, per [the runtime's Skill locations section](../../pstack-runtime/SKILL.md#skill-locations), so check the new skill appears there for the other providers.
2. Validate the skill: frontmatter has `name` and `description`, referenced files exist, cross-skill links resolve.
3. Test cases if structural. Skip if subjective.
4. Run **Opening a PR**.

When in doubt, delete. Keep only prose that changes a decision. Tell it to do the thing and skip the reason. Explain only when the rule is confusing without one. Match tone to scope. Point at structural sources (types, READMEs, config) per the **encode-lessons-in-structure** principle skill. Delegate to other skills by path. Don't restate. A workflow you keep hitting but isn't captured → propose a new skill.

**Reply:** summary of the skill, key design decisions, validation notes.
