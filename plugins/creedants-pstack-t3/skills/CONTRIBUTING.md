# Contributing

Issues and pull requests are welcome.

## Where changes go

- **A skill behaves wrong in T3.** Change its port in `t3/overrides/`, or `t3/runtime.md` if the problem is how pstack maps onto T3's tools. Never edit `skills/` or `vendor/` by hand. `skills/` is generated, and `vendor/pstack` must stay byte-identical to upstream.
- **The engineering content itself (a playbook step, a principle, a rubric).** That belongs upstream in [cursor/plugins](https://github.com/cursor/plugins/tree/main/pstack). pstack-t3 picks it up on the next sync.
- **Installer or roles resolver.** `scripts/install.py` and `t3/scripts/roles.py`, with a test in `tests/`.

[AGENTS.md](AGENTS.md) has the porting rules. Agents working on this repo should read it first.

## Before you open a PR

```bash
pip install pyyaml
python3 scripts/build.py
python3 -m unittest discover -s tests -v
```

Commit the regenerated `skills/` with your change. For a user-facing change, add one fragment under `changes/`. The file name is the branch name with `%` encoded as `%25` and `/` encoded as `%2F`, then `.md`. Encode `%` before `/`. Branch `pstack-t3/d50` writes `changes/pstack-t3%2Fd50.md`. The file holds markdown bullets only. A bullet starts with `- `. Indent a continuation line under that bullet. A branch reused before the release adds its next bullet to the same file. CI fails if `skills/` does not match what the build produces.

Edit `README.md` or `docs/guide.md` only when the ticket is about those files, or when the change removes or renames something they name. Otherwise list the doc edit under follow-ups. Those notes become one docs change. When one coordinator owns those files, that coordinator takes the change. When none does, each coordinator's notes are one batch.

If you changed a skill's behavior, run it in a real T3 thread and say in the PR which provider led and what it did.

## Syncing upstream

Before you sync, see what upstream changed. This reads upstream in a temporary clone and writes nothing in the checkout.

```bash
python3 scripts/sync_upstream.py --check
```

It prints `up to date (<commit>)` when upstream is at the pinned commit. Otherwise it prints the new commit and one row for each changed, added, or removed path under `pstack/`. Each row ends with what pstack-t3 does with that path, which is `overridden by <file under t3/>`, `dropped by t3/removed.txt`, `ships unchanged`, or `not shipped`. Add `--json` for one JSON object a script can read, `--ref` to read a branch, tag, or commit, and `--repository` to read another upstream. A git or network failure exits 1 with git's error.

Then sync.

```bash
python3 scripts/sync_upstream.py
```

The build then lists each override whose upstream file changed. Re-port each one against the new upstream text, then run `python3 scripts/build.py --update-lock`.

## Releasing

1. Print the section. This changes nothing.

```bash
python3 scripts/release.py --dry-run X.Y.Z
```

2. Read the section. It is a `## X.Y.Z (YYYY-MM-DD)` heading with today's date, then one group of bullets per fragment. `--date YYYY-MM-DD` sets another date.
3. Run it for real. The script writes that section above the latest heading in `CHANGELOG.md` and deletes the fragments. It never stages, commits, tags, pushes, or calls `gh`. It prints steps 4 and 5 when it finishes.

```bash
python3 scripts/release.py X.Y.Z
```

4. Commit `CHANGELOG.md` and the deleted fragments in one commit. Tag `vX.Y.Z` on the commit that lands on main, and push the tag.
5. Run `gh release create vX.Y.Z --notes-file <that changelog section>`.

The script orders the fragments by the commit that added each one. It reads this log with `--no-renames` added, and it orders the fragments that one commit added by name.

```bash
git log --reverse --diff-filter=A --format= --name-only -- changes/
```

To check the order by hand, read that log. Skip blank lines. Skip a path that is no longer a file. When the log lists a path more than once, the later line is the one that orders it.

The script exits 1, names the fix, and changes nothing when one of these holds:

- `CHANGELOG.md` or `changes/` has uncommitted changes.
- `CHANGELOG.md` is missing or is a symlink.
- `CHANGELOG.md` already has a `## X.Y.Z` heading, or the version is not above the latest heading.
- `changes/` holds no fragments, or holds an entry that is not a `.md` file.
- A fragment holds a line that is not a bullet or a continuation line.
- The clone is shallow, or no commit added a fragment that sits in `changes/`.

The script writes `CHANGELOG.md` through a temporary file and then deletes the fragments. It holds `SIGINT`, `SIGTERM`, and `SIGHUP` for that whole step. When a write or a delete fails, or one of those signals arrives, it writes `CHANGELOG.md` back and re-creates each deleted fragment from the bytes it read first. It then checks every file against those bytes. It prints `nothing changed` and exits 1 only when the check passes. Otherwise it names each file that differs and prints the command below. A kill that cannot be caught, or power loss, can leave a partial run. The command below restores that too.

To undo a finished or partial run before you commit it, run this. It works whether or not you ran `git add`.

```bash
git restore --staged --worktree CHANGELOG.md changes/
```

Cut a release after each upstream sync and any user-facing fix.
