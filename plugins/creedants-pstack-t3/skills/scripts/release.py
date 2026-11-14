#!/usr/bin/env python3
"""Cut a release section in CHANGELOG.md from the fragments in changes/.

Orders the fragments by the commit that added each one, writes their bullets
under a new `## X.Y.Z (YYYY-MM-DD)` heading, and deletes the fragments. It
never stages, commits, tags, pushes, or calls gh. It prints those steps.

A failed write or delete, or a SIGINT, SIGTERM, or SIGHUP, puts CHANGELOG.md and every fragment back
as the script read them. The script then checks them and prints `nothing changed` only when they match.
When a file differs, it names that file and the undo command. A kill that cannot be caught, or power
loss, can leave a partial run. The same undo command restores it.
"""

from __future__ import annotations

import argparse
import datetime
import os
import re
import signal
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
HEADING = re.compile(r"## ([0-9]+)\.([0-9]+)\.([0-9]+)(?:\s.*)?")
# From 3.11 date.fromisoformat also takes 20261009. The pattern keeps 3.10 and 3.12 equal.
DAY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
# --staged --worktree undoes a run whether or not `git add` already staged it.
UNDO = "git restore --staged --worktree CHANGELOG.md changes/"
HELD = tuple(getattr(signal, name) for name in ("SIGINT", "SIGTERM", "SIGHUP") if hasattr(signal, name))
COMMIT = "\x01"
# --no-renames lists a moved fragment as an add. -z stops git quoting a path.
# --no-show-signature keeps log.showSignature from printing text ahead of the commit marker.
LOG = ("log", "--reverse", "--diff-filter=A", "--no-renames", "--no-show-signature", "-z",
       f"--format=%x{ord(COMMIT):02x}", "--name-only", "--", "changes/")

Version = tuple[int, int, int]


@dataclass(frozen=True)
class Original:
    path: Path
    data: bytes
    mode: int


@dataclass(frozen=True)
class Cut:
    section: str
    changelog: str
    before: Original
    fragments: tuple[Original, ...]


def git(*args: str) -> str:
    try:
        result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                                errors="surrogateescape", env={**os.environ, "LC_ALL": "C"})
    except OSError as error:
        sys.exit(f"git {args[0]} failed: {error}")
    if result.returncode != 0:
        sys.exit(f"git {args[0]} failed: {(result.stderr or result.stdout).strip()}")
    return result.stdout


def parse_version(text: str) -> Version | None:
    match = VERSION.fullmatch(text)
    return tuple(int(part) for part in match.groups()) if match else None


def parse_day(text: str) -> datetime.date | None:
    if not DAY.fullmatch(text):
        return None
    try:
        return datetime.date.fromisoformat(text)
    except ValueError:
        return None


def dotted(version: Version) -> str:
    return ".".join(str(part) for part in version)


def bullet_fault(lines: list[str]) -> str | None:
    open_bullet = False
    for number, line in enumerate(lines, 1):
        bullet = line.startswith("- ") and line[2:].strip()
        continuation = open_bullet and line.startswith((" ", "\t")) and line.strip()
        if "\r" in line or not (bullet or continuation):
            return f"line {number} is not a bullet or a continuation line"
        open_bullet = True
    return None if open_bullet else "holds no bullet"


def added_at(log: str) -> dict[str, int]:
    """Fragment file name to the ordinal of the last commit that added it.

    Raises ValueError on a record that is neither a commit marker nor a path under changes/.
    """
    at, commit = {}, 0
    for token in log.split("\0"):
        if token == COMMIT:
            commit += 1
            continue
        path = token[1:] if token.startswith("\n") else token
        if not path:
            continue
        if not commit or not path.startswith("changes/"):
            raise ValueError(token)
        if path.count("/") == 1:
            at[path[len("changes/"):]] = commit
    return at


def released(changelog: str) -> list[Version]:
    matches = (HEADING.fullmatch(line) for line in changelog.splitlines())
    return [tuple(int(part) for part in match.groups()) for match in matches if match]


def splice(changelog: str, section: str) -> str:
    lines = changelog.splitlines(keepends=True)
    at = next((index for index, line in enumerate(lines) if line.startswith("## ")), len(lines))
    head, tail = "".join(lines[:at]).rstrip("\n"), "".join(lines[at:])
    return (head + "\n\n" if head else "") + section + ("\n" + tail if tail else "")


def remaining_steps(version: str) -> list[str]:
    return [
        "git add CHANGELOG.md changes/",
        f'git commit -m "release {version}"',
        f'git tag -a v{version} -m "pstack-t3 {version}"    # on the commit that lands on main',
        f"git push origin v{version}",
        f"gh release create v{version} --notes-file <release notes file>",
    ]


def read_utf8(path: Path) -> Original:
    data = path.read_bytes()
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        sys.exit(f"{path.relative_to(ROOT).as_posix()} is not UTF-8; fix it")
    return Original(path, data, stat.S_IMODE(path.stat().st_mode))


def refuse_unfinished_release() -> None:
    dirty = git("status", "--porcelain", "--untracked-files=all", "--", "CHANGELOG.md", "changes/")
    if dirty:
        sys.exit("CHANGELOG.md or changes/ has uncommitted changes; commit them, "
                 f"or run {UNDO} to undo an unfinished release:\n{dirty.rstrip()}")


def plan(version_text: str, date_text: str | None) -> Cut:
    version = parse_version(version_text)
    if version is None:
        sys.exit(f"version {version_text} is not X.Y.Z; pass three numbers such as 0.3.0")
    day = datetime.date.today() if date_text is None else parse_day(date_text)
    if day is None:
        sys.exit(f"date {date_text} is not YYYY-MM-DD; pass a real date such as 2026-10-09")

    if git("rev-parse", "--is-shallow-repository").strip() == "true":
        sys.exit("this clone is shallow, so git cannot tell when each fragment was added; "
                 "run git fetch --unshallow and rerun")
    refuse_unfinished_release()

    changelog_path = ROOT / "CHANGELOG.md"
    if changelog_path.is_symlink():
        sys.exit("CHANGELOG.md is a symlink; replace it with the file before you release")
    if not changelog_path.is_file():
        sys.exit("CHANGELOG.md is missing; this script adds a section to an existing changelog")
    before = read_utf8(changelog_path)
    changelog = before.data.decode("utf-8")
    versions = released(changelog)
    if version in versions:
        sys.exit(f"CHANGELOG.md already has a ## {dotted(version)} heading; pick the next version")
    if versions and version < max(versions):
        sys.exit(f"{dotted(version)} is not above {dotted(max(versions))}, the latest version in CHANGELOG.md; "
                 "pick a higher version")

    changes = ROOT / "changes"
    entries = sorted(changes.iterdir()) if changes.is_dir() else []
    if not entries:
        sys.exit("changes/ holds no fragments; there is nothing to release")
    for entry in entries:
        if entry.is_symlink() or not entry.is_file() or not entry.name.endswith(".md"):
            sys.exit(f"changes/{entry.name} is not a fragment; changes/ holds only .md files, so move or delete it")
    originals = {entry.name: read_utf8(entry) for entry in entries}
    bullets = {}
    for entry in entries:
        lines = originals[entry.name].data.decode("utf-8").split("\n")
        bullets[entry.name] = lines[:-1] if lines[-1] == "" else lines
        fault = bullet_fault(bullets[entry.name])
        if fault:
            sys.exit(f"changes/{entry.name} {fault}; fix the fragment, commit it, and rerun")

    try:
        at = added_at(git(*LOG))
    except ValueError as error:
        sys.exit(f"git log printed {str(error)!r}, which is not a commit marker or a path under changes/; "
                 "look in git config for a setting that adds output to git log")
    for entry in entries:
        if entry.name not in at:
            sys.exit(f"git log shows no commit that added changes/{entry.name}; commit the fragment and rerun")
    ordered = sorted(entries, key=lambda entry: (at[entry.name], entry.name))

    body = "".join(line + "\n" for entry in ordered for line in bullets[entry.name])
    section = f"## {dotted(version)} ({day.isoformat()})\n\n{body}"
    return Cut(section=section, changelog=splice(changelog, section), before=before,
               fragments=tuple(originals[entry.name] for entry in ordered))


def write_file(path: Path, data: bytes, mode: int) -> None:
    """Replace path with data in one os.replace, so a reader sees the old file or the new one."""
    handle, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "wb") as temp:
            temp.write(data)
        os.chmod(name, mode)
        os.replace(name, path)
    except BaseException:
        try:
            os.unlink(name)
        except OSError:
            pass
        raise


def found(original: Original) -> tuple[bytes, int] | None:
    try:
        return original.path.read_bytes(), stat.S_IMODE(original.path.stat().st_mode)
    except OSError:
        return None


def differing(cut: Cut) -> list[Original]:
    return [original for original in (cut.before, *cut.fragments)
            if found(original) != (original.data, original.mode)]


def restore(cut: Cut) -> dict[Path, OSError]:
    """Write back each file that differs from what plan read. A second run does nothing."""
    failed = {}
    for original in differing(cut):
        try:
            write_file(original.path, original.data, original.mode)
        except OSError as error:
            failed[original.path] = error
    return failed


def apply(cut: Cut) -> None:
    """Write the changelog, then delete the fragments, holding SIGINT, SIGTERM, and SIGHUP throughout.

    A failure or a caught signal puts every file back, whichever step it stopped at.
    """
    caught: list[int] = []
    previous = {}
    try:
        for number in HELD:
            previous[number] = signal.signal(number, lambda signum, frame: caught.append(signum))
        steps = [lambda: write_file(cut.before.path, cut.changelog.encode("utf-8"), cut.before.mode),
                 *(fragment.path.unlink for fragment in cut.fragments)]
        reason = None
        try:
            for step in steps:
                if caught:
                    break
                step()
        except (Exception, KeyboardInterrupt) as error:
            reason = "interrupted" if isinstance(error, KeyboardInterrupt) else str(error) or type(error).__name__
        if caught:
            reason = reason or "interrupted"
        if reason is None:
            return
        failed = restore(cut)
        left = [original.path for original in differing(cut)]
        if left:
            named = ", ".join(
                f"{path.relative_to(ROOT).as_posix()} ({failed[path]})" if path in failed
                else path.relative_to(ROOT).as_posix()
                for path in left)
            sys.exit(f"stopped partway: {reason}; could not put back {named}; run {UNDO} to undo, then rerun")
        sys.exit(f"stopped partway: {reason}; nothing changed, fix that and rerun")
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="the version to cut, as X.Y.Z")
    parser.add_argument("--dry-run", action="store_true", help="print the section and change nothing")
    parser.add_argument("--date", help="the date in the heading, as YYYY-MM-DD (default: today)")
    args = parser.parse_args(argv)
    cut = plan(args.version, args.date)
    sys.stdout.write(cut.section)
    sys.stdout.flush()
    if not args.dry_run:
        apply(cut)
    wrote, deleted = ("would write", "would delete") if args.dry_run else ("wrote", "deleted")
    print(f"\n{wrote} this section to CHANGELOG.md")
    for fragment in cut.fragments:
        print(f"{deleted} changes/{fragment.path.name}")
    if args.dry_run:
        print("nothing changed")
    print("this script never stages, commits, tags, or pushes. the remaining steps:")
    for step in remaining_steps(args.version):
        print(f"  {step}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
