# Move an existing installation to skills

Older installations deliver a compiled Markdown profile. Migration keeps that learning, saves your original skill library, and publishes the supported guidance into skills and native instructions. It never changes native memory. New installations need no migration.

## Preview

Run this from a repository whose scoped learning you want to keep:

```bash
shadowclone migrate skills --repo /path/to/repository
```

The preview reads local state, writes nothing, and calls no model. Repeat `--repo` to register more repositories. Without it, the command uses the current directory. Learning for an unregistered repository stays unpublished.

## Publish

```bash
shadowclone migrate skills --apply --automatic --memory --repo /path/to/repository
```

- `--automatic` authorizes supported edits to the skills that you own.
- `--memory` turns on recurring read-only Claude memory extraction for the registered repositories.

An omitted flag keeps its current setting.

Apply saves the original library and native instructions, then publishes in reversible batches with the authenticated agent CLI and the learning budget. Repeat the command to continue. Completed work stays.

Run `shadowclone skills pending` to inspect what remains unpublished. Resolve conflicting edits, then run `skills retry <key>` to queue a record or `skills exclude <key> <reason>` to exclude it. `shadowclone skills update` processes pending work when your maintenance consent allows.

## Activate

```bash
shadowclone migrate skills --apply --activate-only
shadowclone context --explain
```

Activation makes no model call. It needs coverage of the applicable learning, a published baseline, and matching file fingerprints. An unresolved scope or a changed file stops the switch. The legacy profile files stay as recovery files. Reverse changes with `history` and `undo <revision>`.

## Before migration

These commands work on profile installations:

- `shadowclone profile repair` previews repairs. `--decisions <file>` supplies reviewed choices, and `--apply` writes them.
- `shadowclone migrate claude-memory` previews the older one-time memory import.
- `shadowclone skills show <id>`, `apply <id>`, and `reject <id>` handle a legacy proposal. `skills manage <skill-id>` authorizes legacy managed additions for a skill.

After migration, use [skill maintenance](skills.md).
