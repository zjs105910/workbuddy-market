#!/usr/bin/env python3
"""Install pstack-t3 skills into every provider skill directory T3 reads.

T3's `$` picker lists each provider's native skills, so pstack-t3 links its
generated skills into each provider's directory. Every link and every entry
moved aside is recorded in a manifest so `uninstall` restores the prior state.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import fcntl
import hashlib
import json
import os
import shlex
import shutil
import stat
import sys
import tempfile
import time
from contextlib import ExitStack, contextmanager, suppress
from dataclasses import dataclass, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
HARNESSES = ("claude", "codex", "grok", "cursor")
LEGACY_NAME = "install-manifest.json"
OWNERS_DIR = "install-owners"
SKIPPED = 3


def skill_dirs(scope_root, user):
    home = Path(os.environ.get("HOME", str(Path.home())))
    claude = Path(os.environ["CLAUDE_CONFIG_DIR"]) if user and os.environ.get("CLAUDE_CONFIG_DIR") else (home / ".claude" if user else scope_root / ".claude")
    base = home if user else scope_root
    return {
        "claude": claude / "skills",
        "codex": base / ".agents" / "skills",
        "grok": base / ".grok" / "skills",
        "cursor": base / ".cursor" / "skills",
    }


def extra_dirs(scope_root, user):
    """Other directories each provider also reads skills from, where stale copies can compete."""
    home = Path(os.environ.get("HOME", str(Path.home())))
    base = home if user else scope_root
    claude = skill_dirs(scope_root, user)["claude"]
    return {
        "claude": [],
        "codex": [base / ".codex" / "skills"],
        "grok": [],
        "cursor": [base / ".agents" / "skills", base / ".codex" / "skills", claude],
    }


def state_dir(scope_root, user):
    if user:
        config = Path(os.environ.get("XDG_CONFIG_HOME") or Path(os.environ.get("HOME", str(Path.home()))) / ".config")
        return config / "pstack-t3"
    return scope_root / ".pstack"


def owner_path(state, checkout):
    digest = hashlib.sha256(str(checkout).encode()).hexdigest()[:16]
    return Path(state) / OWNERS_DIR / f"{digest}.json"


def link_target(checkout, path):
    return os.path.join(str(checkout), "skills", os.path.basename(path))


def proves(checkout, entry, original):
    try:
        text = os.readlink(entry)
    except OSError:
        return False
    base = os.path.realpath(os.path.dirname(original))
    return os.path.normpath(os.path.join(base, text)) == link_target(checkout, original)


def identity(stat):
    return stat.st_dev, stat.st_ino, stat.st_ctime_ns


# Linux opens the entry itself with O_PATH. macOS opens a symlink itself with O_SYMLINK, and O_NONBLOCK keeps a FIFO from blocking.
HOLD_FLAGS = (os.O_PATH | os.O_NOFOLLOW) if hasattr(os, "O_PATH") else (os.O_RDONLY | getattr(os, "O_SYMLINK", os.O_NOFOLLOW) | os.O_NONBLOCK)


def hold(path, holds):
    """Open the entry at `path` itself and keep it open until `holds` closes. Return what restore needs to prove it is still there."""
    try:
        fd = os.open(path, HOLD_FLAGS)
    except OSError as error:
        return Held(None, None, error.strerror or str(error))
    holds.callback(os.close, fd)
    return Held(fd, identity(os.fstat(fd)))


def slot_of(path):
    return (os.path.realpath(os.path.dirname(path)), os.path.basename(path))


def ordered(harnesses):
    have = {harness for harness in harnesses if harness in HARNESSES}
    return tuple(harness for harness in HARNESSES if harness in have)


def inside_checkout(path):
    real = Path(os.path.realpath(path))
    skills = Path(os.path.realpath(SKILLS))
    return real == skills or skills in real.parents


def describe(path):
    if os.path.islink(path):
        return f"link to {os.readlink(path)}"
    return "directory" if os.path.isdir(path) else "file"


@dataclass(frozen=True)
class LinkRec:
    raw: object
    path: str
    harnesses: tuple
    checkout: str | None


@dataclass(frozen=True)
class BackupRec:
    raw: object
    original: str
    backup: str
    harnesses: tuple


@dataclass(frozen=True)
class View:
    claims: dict
    links: tuple
    backups: tuple


@dataclass(frozen=True)
class Mine:
    path: str
    harnesses: tuple
    claim_paths: tuple
    tagged: tuple
    voucher: object


@dataclass(frozen=True)
class Held:
    """A descriptor open on a backup from the plan to its restore. An inode in use keeps its number, so no new entry can share it."""
    fd: int | None
    entry: tuple | None
    error: str | None = None


@dataclass(frozen=True)
class Step:
    kind: str
    path: str
    backup: str | None = None
    place: str = ""
    harnesses: tuple = ()
    add_claims: tuple = ()
    add_links: tuple = ()
    add_backups: tuple = ()
    remove_claims: tuple = ()
    remove_links: tuple = ()
    remove_backups: tuple = ()
    adopted: bool = False
    held: Held | None = None


@dataclass(frozen=True)
class Plan:
    steps: tuple = ()
    conflicts: tuple = ()
    refusals: tuple = ()
    untracked: int = 0
    adopted: int = 0
    occupied: tuple = ()
    shared: tuple = ()
    kept: int = 0


def harnesses_for(path, entry, scope, user):
    if isinstance(entry, dict) and isinstance(entry.get("harnesses"), list):
        return ordered(entry["harnesses"])
    if isinstance(entry, dict) and isinstance(entry.get("harness"), str) and entry["harness"] in HARNESSES:
        return (entry["harness"],)
    parent = os.path.realpath(os.path.dirname(path))
    found = [harness for harness, directory in skill_dirs(scope, user).items() if os.path.realpath(directory) == parent]
    return ordered(found) if found else HARNESSES


def parse_link(entry, scope, user):
    if isinstance(entry, str):
        return LinkRec(entry, entry, harnesses_for(entry, None, scope, user), None)
    if not isinstance(entry, dict):
        return None
    path = entry.get("path")
    if not isinstance(path, str):
        return None
    checkout = entry.get("checkout") if isinstance(entry.get("checkout"), str) else None
    return LinkRec(entry, path, harnesses_for(path, entry, scope, user), checkout)


def parse_backup(entry, scope, user):
    if not isinstance(entry, dict):
        return None
    original, backup = entry.get("original"), entry.get("backup")
    if not isinstance(original, str) or not isinstance(backup, str):
        return None
    return BackupRec(entry, original, backup, harnesses_for(original, entry, scope, user))


class Unreadable(Exception):
    """A record file that cannot be used. Its text is the line install and uninstall exit 1 with."""


def read_object(path):
    try:
        data = json.loads(path.read_text())
    except ValueError:
        raise Unreadable(f"{path} is not valid JSON; fix or move it and rerun") from None
    if not isinstance(data, dict):
        raise Unreadable(f"{path} is not a JSON object; fix or move it and rerun")
    return data


def legacy_lists(path):
    data = read_object(path)
    found = []
    for key in ("links", "backups"):
        value = data.get(key, [])
        if not isinstance(value, list):
            raise Unreadable(f"{path} has a {key} entry that is not a list; fix or move it and rerun")
        found.append(value)
    return data, found[0], found[1]


def read_legacy(state, scope, user):
    path = Path(state) / LEGACY_NAME
    if not path.exists():
        return (), ()
    _data, raw_links, raw_backups = legacy_lists(path)
    links = tuple(item for item in (parse_link(entry, scope, user) for entry in raw_links) if item)
    backups = tuple(item for item in (parse_backup(entry, scope, user) for entry in raw_backups) if item)
    return links, backups


def load(scope, user):
    state = state_dir(scope, user)
    root = str(ROOT)
    links, backups = read_legacy(state, scope, user)
    return View(current_claims(state, root), links, backups)


def records(view, root):
    parts = {}

    def bucket(path):
        return parts.setdefault(slot_of(path), {"claims": [], "tagged": [], "untagged": []})

    for path, harnesses in view.claims.items():
        bucket(path)["claims"].append((path, harnesses))
    for link in view.links:
        if link.checkout == root:
            bucket(link.path)["tagged"].append(link)
        elif link.checkout is None:
            bucket(link.path)["untagged"].append(link)
    present = stacks(view)
    found = {}
    for slot, group in parts.items():
        live = None
        for path, _harnesses in group["claims"]:
            if proves(root, path, path):
                live = path
                break
        if live is None:
            for link in group["tagged"] + group["untagged"]:
                if proves(root, link.path, link.path):
                    live = link.path
                    break
        proving_live = live is not None
        proving = proving_live or set_aside(present, root, slot)
        claims = group["claims"]
        tagged = group["tagged"]
        untagged = group["untagged"]
        if not (claims or tagged or (untagged and proving)):
            continue
        if live is None:
            if claims:
                live = claims[0][0]
            elif tagged:
                live = tagged[0].path
            else:
                live = untagged[0].path
        harnesses = ordered(
            [harness for _path, owned in claims for harness in owned]
            + [harness for link in tagged + untagged for harness in link.harnesses]
        )
        voucher = untagged[-1].raw if untagged and proving_live and not tagged else None
        found[slot] = Mine(live, harnesses, tuple(path for path, _owned in claims), tuple(tagged), voucher)
    return found


def set_aside(present, root, slot):
    """Whether a present backup row of `slot` holds this checkout's link. `present` is `stacks(view)`."""
    return any(proves(root, row.backup, row.original) for row in present.get(slot, ()))


def stacks(view):
    found = {}
    for row in view.backups:
        if os.path.lexists(row.backup):
            found.setdefault(slot_of(row.original), []).append(row)
    return found


def layout(scope, user, selected):
    directories = skill_dirs(scope, user)
    user_dirs = {}
    if not user:
        for directory in skill_dirs(None, True).values():
            user_dirs.setdefault(os.path.realpath(directory), directory)
    grouped = {}
    for harness in HARNESSES:
        directory = directories[harness]
        grouped.setdefault(os.path.realpath(directory), []).append((harness, directory))
    chosen = set(selected)
    groups, refusals = [], []
    for real, members in grouped.items():
        harnesses = tuple(harness for harness, _directory in members)
        if not chosen.intersection(harnesses):
            continue
        directory = members[0][1]
        label = next(harness for harness, _directory in members if harness in chosen)
        shown = directories[label]
        if real in user_dirs:
            refusals.append(f"{label}: {shown} already resolves to {user_dirs[real]}; nothing to link")
            continue
        if inside_checkout(directory):
            refusals.append(f"{label}: {shown} already resolves to {SKILLS}; nothing to link")
            continue
        groups.append((str(directory), harnesses))
    return groups, refusals


def tagged_exists(view, path, root):
    return any(link.checkout == root and link.path == path for link in view.links)


def plan_install(view, scope, user, selected, names, root, replace):
    groups, refusals = layout(scope, user, selected)
    owned = records(view, root)
    steps, conflicts = [], []
    untracked = adopted = 0
    for directory, harnesses in groups:
        for name in names:
            path = os.path.join(directory, name)
            if proves(root, path, path):
                record = owned.get(slot_of(path))
                if record is None:
                    untracked += 1
                else:
                    union = ordered(record.harnesses + harnesses)
                    if not record.claim_paths or set(union) != set(record.harnesses):
                        if not record.claim_paths:
                            adopted += 1
                        steps.append(Step("record", path, harnesses=union, add_claims=((path, union),), adopted=not record.claim_paths))
                continue
            # Moving a path that is this checkout's own skill directory would relocate the checkout.
            if inside_checkout(path):
                continue
            if os.path.lexists(path):
                conflicts.append((harnesses, path))
                if replace:
                    steps.append(Step("move", path, place=f"{harnesses[0]}/{name}", harnesses=harnesses))
            if not os.path.lexists(path) or replace:
                row = {"harnesses": list(harnesses), "path": path, "checkout": root}
                add_links = () if tagged_exists(view, path, root) else (row,)
                steps.append(Step("create", path, harnesses=harnesses, add_claims=((path, harnesses),), add_links=add_links))
    return Plan(tuple(steps), tuple(conflicts), tuple(refusals), untracked, adopted)


def occupied_note(row):
    path, backup = row.original, row.backup
    if os.path.islink(path):
        spelled = os.path.normpath(os.path.join(os.path.dirname(path), os.readlink(path)))
        parent = os.path.dirname(spelled)
        if os.path.basename(spelled) == os.path.basename(path) and os.path.basename(parent) == "skills":
            checkout = os.path.dirname(parent)
            if not os.path.exists(checkout):
                return (f"kept backup {backup}: {path} is occupied by a link into deleted checkout {checkout}; "
                        "remove it and rerun uninstall")
    return f"kept backup {backup}: {path} is occupied; clear it and rerun uninstall"


def plan_uninstall(view, root, selected, holds):
    chosen = set(selected)
    shared = set()
    owned = records(view, root)
    present = stacks(view)

    def selected_row(harnesses):
        have = set(harnesses)
        if have <= chosen:
            return True
        if have & chosen:
            shared.add(", ".join(sorted(have - chosen)))
        return False

    steps = []
    occupied = []
    withdrawn = set()
    uncovered = set()
    kept = 0
    for slot, record in owned.items():
        if not selected_row(record.harnesses):
            continue
        rows = present.get(slot, ())
        consumers = []
        for row in rows:
            if proves(root, row.backup, row.original) and contested_by(row.backup) is None:
                consumers.append(Step("withdraw", record.path, backup=row.backup, remove_backups=(row.backup,)))
                withdrawn.add(row.backup)
        unlinks = proves(root, record.path, record.path)
        if unlinks:
            consumers.append(Step("unlink", record.path))
            uncovered.add(slot)
        steps.extend(consumers)
        # A live entry over a withdrawn top backup covered this link; any other live entry is a repoint.
        consumed = unlinks or not os.path.lexists(record.path) or bool(rows and rows[-1].backup in withdrawn)
        if not consumers or not consumed:
            kept += len(record.claim_paths)
            continue
        links = tuple(link.raw for link in record.tagged)
        if record.voucher is not None:
            links = links + (record.voucher,)
        if record.claim_paths or links:
            steps.append(Step("forget", record.path, remove_claims=record.claim_paths, remove_links=links))
    for slot, rows in present.items():
        remaining = [row for row in rows if row.backup not in withdrawn]
        if not remaining:
            continue
        top = remaining[-1]
        free = slot in uncovered or not os.path.lexists(top.original)
        if free and (slot in uncovered or selected_row(top.harnesses)):
            aside = contested_by(top.backup)
            if aside is None:
                steps.append(Step("restore", top.original, backup=top.backup, remove_backups=(top.backup,), held=hold(top.backup, holds)))
            else:
                occupied.append(f"kept backup {top.backup}: {aside} is held for that path and another entry is there now; "
                                "remove the one that is not the backup and rerun uninstall")
        elif not free and selected_row(top.harnesses):
            occupied.append(occupied_note(top))
    return Plan(tuple(steps), occupied=tuple(occupied), shared=tuple(sorted(shared)), kept=kept)


def atomic_write(directory, name, text):
    directory.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=directory)
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(text)
        os.replace(temporary, directory / name)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise


def write_claims(state, root, claims):
    path = owner_path(state, root)
    if not claims:
        if path.exists():
            path.unlink()
        return
    body = {"checkout": root, "links": {key: {"harnesses": list(claims[key])} for key in claims}}
    atomic_write(path.parent, path.name, json.dumps(body, indent=2) + "\n")


def current_claims(state, root):
    path = owner_path(state, root)
    if not path.exists():
        return {}
    data = read_object(path)
    recorded = data.get("checkout")
    if recorded != root:
        raise Unreadable(f"{path} records {recorded}, not this checkout")
    return claims_in(data)


def claims_in(data):
    links = data.get("links")
    if not isinstance(links, dict):
        return {}
    claims = {}
    for key, value in links.items():
        harnesses = value.get("harnesses") if isinstance(value, dict) else None
        if isinstance(key, str) and isinstance(harnesses, list):
            claims[key] = ordered(harnesses)
    return claims


def patch_legacy(state, add_links, add_backups, remove_links, remove_backups, adding):
    """Return the link and backup rows this call appended."""
    if not add_links and not add_backups and not remove_links and not remove_backups:
        return (), ()
    path = Path(state) / LEGACY_NAME
    # Older installers still read this file, so a cleanup leaves empty lists in place.
    if path.exists():
        data, links, backups = legacy_lists(path)
    elif adding:
        data, links, backups = {}, [], []
    else:
        return (), ()
    added_links, added_backups = [], []
    changed = False
    if adding:
        for row in add_links:
            if isinstance(row, dict) and any(
                isinstance(have, dict) and have.get("path") == row.get("path") and have.get("checkout") == row.get("checkout")
                for have in links
            ):
                continue
            links.append(row)
            added_links.append(row)
            changed = True
        for row in add_backups:
            backups.append(row)
            added_backups.append(row["backup"])
            changed = True
    else:
        for raw in remove_links:
            for index in range(len(links) - 1, -1, -1):
                if links[index] == raw:
                    del links[index]
                    changed = True
                    break
        for backup in remove_backups:
            for index in range(len(backups) - 1, -1, -1):
                have = backups[index]
                if isinstance(have, dict) and have.get("backup") == backup:
                    del backups[index]
                    changed = True
                    break
    if changed:
        data["links"] = links
        data["backups"] = backups
        atomic_write(Path(state), LEGACY_NAME, json.dumps(data, indent=2) + "\n")
    return tuple(added_links), tuple(added_backups)


def add_records(step, state, root):
    """Save a step's adds before its act. Return a function that takes back exactly the records that were new."""
    previous = {}
    if step.add_claims:
        claims = current_claims(state, root)
        for path, harnesses in step.add_claims:
            previous[path] = claims.get(path)
            claims[path] = ordered(harnesses)
        write_claims(state, root, claims)
    links, backups = patch_legacy(state, step.add_links, step.add_backups, (), (), True)

    def undo():
        patch_legacy(state, (), (), links, backups, False)
        if previous:
            claims = current_claims(state, root)
            for path, harnesses in previous.items():
                if harnesses is None:
                    claims.pop(path, None)
                else:
                    claims[path] = harnesses
            write_claims(state, root, claims)

    return undo


def remove_records(step, state, root):
    # Owner file first on add and last on remove, so a crash keeps an extra claim.
    patch_legacy(state, (), (), step.remove_links, step.remove_backups, False)
    if step.remove_claims:
        claims = current_claims(state, root)
        for path in step.remove_claims:
            claims.pop(path, None)
        write_claims(state, root, claims)


def ready(step, root):
    if step.kind == "create":
        return not os.path.lexists(step.path)
    if step.kind == "move":
        return bool(step.backup) and os.path.lexists(step.path) and not os.path.lexists(step.backup)
    if step.kind in ("record", "forget"):
        return True
    if step.kind == "unlink":
        return proves(root, step.path, step.path)
    if step.kind == "withdraw":
        return proves(root, step.backup, step.path)
    if step.kind == "restore":
        return os.path.lexists(step.backup) and not os.path.lexists(step.path)
    return False


def subject(step):
    return {
        "unlink": f"unlink {step.path}",
        "withdraw": f"withdraw {step.backup}",
        "restore": f"restore {step.backup}",
        "create": f"link {step.path}",
        "move": f"move {step.path}",
    }.get(step.kind)


def skip_note(step):
    reason = {
        "unlink": "the link no longer matches the recorded checkout",
        "withdraw": "the backup no longer matches the recorded checkout",
        "restore": f"{step.path} changed before uninstall",
        "create": "it changed before install",
        "move": "it changed before install",
    }.get(step.kind)
    return f"skipped {subject(step)}: {reason}" if reason else None


RENAME_NOREPLACE = 1
AT_FDCWD = -100


def rename_noreplace(source, target):
    """Rename `source` to `target` only while `target` is empty. Return 0, or the errno that stopped it."""
    if not sys.platform.startswith("linux"):
        return errno.ENOSYS
    try:
        renameat2 = ctypes.CDLL(None, use_errno=True).renameat2
    except (OSError, AttributeError):
        return errno.ENOSYS
    renameat2.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    renameat2.restype = ctypes.c_int
    if renameat2(AT_FDCWD, os.fsencode(source), AT_FDCWD, os.fsencode(target), RENAME_NOREPLACE) == 0:
        return 0
    return ctypes.get_errno()


def place(source, path):
    """Move the entry at `source` to `path` only while `path` is still empty. Return 0, or the errno that stopped it.

    `source` is a name only the caller uses, because the link and the unlink each look it up again.
    """
    try:
        # A hard link of the link itself fails on a taken path, where a rename would replace it.
        os.link(source, path, follow_symlinks=False)
    except FileExistsError:
        return errno.EEXIST
    except (OSError, NotImplementedError) as error:
        # A rename cannot cross a filesystem that a hard link cannot.
        if getattr(error, "errno", None) == errno.EXDEV:
            return errno.EXDEV
        # A directory cannot be hard linked. A plain rename would replace whatever took the path since.
        return rename_noreplace(source, path)
    os.unlink(source)
    return 0


def refusal(path, code):
    """Why `place` left its entry where it was, or None when it moved it."""
    if code == 0:
        return None
    if code in (errno.EEXIST, errno.ENOTEMPTY):
        return f"{path} was taken again"
    return f"{path} cannot be refilled without risking an overwrite ({os.strerror(code)})"


def put_back(aside, path):
    """Return the entry at `aside` to `path` only while `path` is still empty. Return why it stayed aside."""
    return refusal(path, place(aside, path))


def discard(path):
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    else:
        os.unlink(path)


HOLDER = ".pstack-t3-"
SCRAP = ".pstack-t3-scrap-"
SCRAP_LEFT = "an unfinished copy or an already restored backup; delete it by hand"


def listing(directory):
    """The names in `directory`, sorted. A directory that is missing or cannot be read has none."""
    try:
        return sorted(os.listdir(directory))
    except OSError:
        return []


def holders(parent):
    for name in listing(parent):
        directory = os.path.join(parent, name)
        if name.startswith(HOLDER) and not os.path.islink(directory) and os.path.isdir(directory):
            yield name, directory


class Stranded(OSError):
    """An OSError that left entries in a holder. Its text is the original error plus where they are kept."""

    def __init__(self, error, kept):
        super().__init__(error.errno, error.strerror)
        self.error = error
        self.kept = tuple(kept)

    def __str__(self):
        return f"{self.error}; it is kept at {', '.join(self.kept)}"


class Holder:
    """A private directory beside `home`. `aside` is the one name an entry takes inside it.

    An entry at `aside` in a HOLDER directory was renamed or hard linked from `home`. Nothing in a SCRAP directory was:
    it holds a copy being built, or a backup whose copy is already in place.
    As a context manager it removes the directory when it leaves empty, and never deletes an entry. An OSError that
    leaves while entries are inside becomes a `Stranded` that names them.
    """

    def __init__(self, home, prefix=HOLDER):
        parent, name = os.path.split(home)
        # A directory this call just created holds nothing yet, so a move into it cannot land on an existing entry.
        # mkdtemp ends the name with characters from [a-z0-9_], so no HOLDER name starts with SCRAP.
        self.directory = tempfile.mkdtemp(prefix=prefix, dir=parent)
        self.home = home
        self.aside = os.path.join(self.directory, name)

    def __enter__(self):
        return self

    def __exit__(self, kind, error, trace):
        left = tuple(os.path.join(self.directory, name) for name in listing(self.directory))
        if not left:
            with suppress(OSError):
                os.rmdir(self.directory)
        elif isinstance(error, Stranded):
            error.kept += left
        elif isinstance(error, OSError):
            raise Stranded(error, left) from error
        return False


def place_copy(source, path):
    """Copy the entry at `source` beside `path`, then place the copy. Return what `place` returned."""
    with Holder(path, SCRAP) as holder:
        copy = holder.aside
        try:
            if os.path.isdir(source) and not os.path.islink(source):
                shutil.copytree(source, copy, symlinks=True)
            else:
                shutil.copy2(source, copy, follow_symlinks=False)
            return place(copy, path)
        finally:
            # A placed copy has left the holder. Anything still at `copy` is this call's own copy.
            if os.path.lexists(copy):
                discard(copy)


def remove_link(path, root, original, noun):
    """Move the link at `path` aside, then delete it only if it is this checkout's link for `original`. Return why it was kept."""
    with Holder(path) as holder:
        aside = holder.aside
        # Another installer can replace the link after the plan proved it; the rename takes whatever is there now.
        os.rename(path, aside)
        if proves(root, aside, original):
            os.unlink(aside)
            return None
        reason = put_back(aside, path)
        if reason is not None:
            return f"the {noun} no longer matches the recorded checkout and {reason}; it is kept at {aside}"
        return f"the {noun} no longer matches the recorded checkout"


CHANGED = "the backup is no longer the entry uninstall read"


def same_entry(path, fd):
    """Whether `path` names the entry `fd` holds open. An inode in use keeps its number, so no other entry can show it."""
    return identity(os.lstat(path))[:2] == identity(os.fstat(fd))[:2]


def link_held(fd, path):
    """Hard link the entry `fd` holds open to `path` only while `path` is empty. Return 0, or the errno that stopped it."""
    if not sys.platform.startswith("linux"):
        return errno.ENOSYS
    try:
        # The descriptor is the entry itself, whatever its old path names now.
        # `src_dir_fd` makes Python call linkat, which follows the /proc link to that entry. Plain link would link the /proc entry itself and fail as a crossing.
        # The source is an absolute path, so the descriptor passed there is never used as a directory.
        os.link(f"/proc/self/fd/{fd}", path, src_dir_fd=fd, follow_symlinks=True)
    except (OSError, NotImplementedError) as error:
        return getattr(error, "errno", None) or errno.ENOSYS
    return 0


def drop_backup(backup, aside, path, fd):
    """Delete the backup that is now at `path`, only if `backup` still names the entry `fd` holds. Any other entry stays and is reported."""
    try:
        # The rename takes whatever the path names now into a directory only this call uses, so the check and the delete see one entry.
        os.rename(backup, aside)
    except FileNotFoundError:
        return
    if same_entry(aside, fd):
        os.unlink(aside)
        return
    reason = put_back(aside, backup)
    if reason is None:
        print(f"kept {backup}: it is not the backup uninstall restored to {path}")
    else:
        print(f"kept {aside}: it took the place of the backup uninstall restored to {path} and {reason}")


def place_proven(aside, path):
    """Move the proven entry at `aside` to `path`, by a copy when `path` is on another filesystem. Return why it stayed."""
    try:
        code = place(aside, path)
        if code != errno.EXDEV:
            return refusal(path, code)
        # The backup is on another filesystem. A copy beside the path takes the same put-back, and the proven entry goes once the copy is in place.
        code = place_copy(aside, path)
    except OSError as error:
        # A copy that failed left nothing at the path, so the entry goes back like one that was refused.
        return str(error)
    if code == 0:
        retire(aside)
    return refusal(path, code)


def retire(aside):
    """Delete the entry at `aside`, whose full copy is now in place.

    It moves into a SCRAP directory beside its holder first, so what a stopped removal leaves is never taken for a backup.
    """
    holder, name = os.path.split(aside)
    with Holder(os.path.join(os.path.dirname(holder), name), SCRAP) as scrap:
        os.rename(aside, scrap.aside)
        discard(scrap.aside)


def restore_aside(backup, aside, path, fd):
    """Restore through the private name `aside` where the descriptor cannot be linked. Return why the backup was kept."""
    try:
        # A second name leaves the backup where it is until the entry is proven.
        os.link(backup, aside, follow_symlinks=False)
        named = True
    except (OSError, NotImplementedError):
        # A directory cannot be hard linked. The no-replace rename that moves it here is the one that can put it back.
        code = rename_noreplace(backup, aside)
        if code != 0:
            return CHANGED if code == errno.ENOENT else refusal(path, code)
        named = False
    reason = place_proven(aside, path) if same_entry(aside, fd) else CHANGED
    if named:
        # Only the second name is left here. The backup still has its own.
        if os.path.lexists(aside):
            os.unlink(aside)
        if reason is None:
            drop_backup(backup, aside, path, fd)
        return reason
    if reason is None:
        return None
    stuck = put_back(aside, backup)
    return reason if stuck is None else f"{reason} and {stuck}; it is kept at {aside}"


def restore_backup(backup, path, held):
    """Move the backup to `path` only while `path` is empty and the backup is the entry the plan held. Return why it was kept."""
    if held.fd is None:
        return f"the backup could not be held open to prove it is the entry uninstall read ({held.error})"
    try:
        now = identity(os.lstat(backup))
    except OSError:
        now = None
    # ext4 hands a freed inode number, and with small inodes its whole-second change time, to the next new entry, so equal numbers alone prove nothing.
    # The held descriptor keeps the planned inode in use, so an entry made since has other numbers. The change time also catches one changed in place.
    if now is None or now[:2] != identity(os.fstat(held.fd))[:2] or now != held.entry:
        return CHANGED
    # The backup's path can name another entry from here on, so every later step acts on the held entry or on one first moved where only this call looks.
    # Another installer can take `path` after the plan saw it empty; each step refuses it instead of replacing it.
    code = link_held(held.fd, path)
    if code == errno.EEXIST:
        return refusal(path, code)
    try:
        holder = Holder(backup)
    except FileNotFoundError:
        # The backup left with its directory, so no name is left to clean up or to restore from.
        return None if code == 0 else CHANGED
    with holder:
        if code == 0:
            drop_backup(backup, holder.aside, path, held.fd)
            return None
        return restore_aside(backup, holder.aside, path, held.fd)


@dataclass(frozen=True)
class Stray:
    """One thing found in a holder directory, and the one action the records allow.

    `kind` is "empty" for a holder with nothing in it, where `path` is the holder. Otherwise `path` is the entry, and
    `kind` is "home" to return it to `home`, "spare" to remove a second name of the entry at `twin`, "own" to remove
    this checkout's link whose `home` is taken, or "left" for an entry that stays because of `why`.
    `drop` is the backup path of a row that a "spare" finishes.
    """
    kind: str
    path: str
    home: str = ""
    twin: str = ""
    drop: str = ""
    why: str = ""


def holder_parents(scope, user, state, selected):
    groups, _refusals = layout(scope, user, selected)
    filed_under = set(selected)
    for directory, harnesses in groups:
        filed_under.update(harnesses)
        yield "skills", directory
    backups = os.path.join(state, "backups")
    for stamp in listing(backups):
        for name in listing(os.path.join(backups, stamp)):
            if name in HARNESSES and name not in filed_under:
                continue
            yield "backups", os.path.join(backups, stamp, name)


def owns(view, root, home):
    """Whether this checkout's claim, or a link row for it, names the slot of `home`."""
    return slot_of(home) in records(view, root)


def one_entry(first, second):
    """Whether both paths name one entry that is not a directory, so that removing one name deletes nothing."""
    try:
        one, other = os.lstat(first), os.lstat(second)
    except OSError:
        return False
    return os.path.samestat(one, other) and not stat.S_ISDIR(one.st_mode)


def contested_by(backup):
    if not os.path.lexists(backup):
        return None
    parent, name = os.path.split(backup)
    for _holder, directory in holders(parent):
        aside = os.path.join(directory, name)
        if os.path.lexists(aside) and not one_entry(aside, backup):
            return aside
    return None


def judge(view, root, side, aside, home):
    """Return the Stray for the entry at `aside`, which a HOLDER directory holds for `home`. Reads only."""
    if one_entry(aside, home):
        return Stray("spare", aside, home, twin=home)
    rows = [row for row in view.backups if row.backup == home] if side == "backups" else []
    if rows:
        if os.path.lexists(home):
            return Stray("left", aside, home, why=f"{home} is the recorded backup of {rows[-1].original} and another entry is there now")
        for row in rows:
            if one_entry(aside, row.original):
                return Stray("spare", aside, home, twin=row.original, drop=row.backup)
        return Stray("home", aside, home)
    if side == "skills" and owns(view, root, home) and proves(root, aside, home):
        return Stray("own" if os.path.lexists(home) else "home", aside, home)
    if side == "backups":
        return Stray("left", aside, home, why=f"no backup record names {home}")
    return Stray("left", aside, home, why=f"it is not a link this checkout recorded at {home}")


def survey(view, scope, user, state, root, selected):
    found = []
    for side, parent in holder_parents(scope, user, state, selected):
        for name, directory in holders(parent):
            entries = listing(directory)
            if not entries:
                found.append(Stray("empty", directory))
            for entry in entries:
                aside, home = os.path.join(directory, entry), os.path.join(parent, entry)
                if name.startswith(SCRAP):
                    found.append(Stray("left", aside, home, why=SCRAP_LEFT))
                else:
                    found.append(judge(view, root, side, aside, home))
    return tuple(found)


def backup_place(state, backup):
    """Return (stamp, harness) when `backup` is spelled <state>/backups/<stamp>/<harness>/<name>, else None.

    The inverse of the path `execute` builds for a move. It compares text only and resolves nothing.
    """
    top = os.path.join(str(state), "backups") + os.sep
    if not backup.startswith(top):
        return None
    parts = backup[len(top):].split(os.sep)
    if len(parts) != 3 or any(part in ("", ".", "..") for part in parts):
        return None
    return parts[0], parts[1]


def prune(state, backup):
    """Remove the <harness> directory `backup` was in if it is empty, then its <stamp> directory if that is empty.

    It removes only empty directories at those two levels, under `state`/backups. It never follows a symlink at
    backups/, <stamp>, or <harness>. A symlink at `state` or above it is followed like any other path to the state
    directory, so a state directory kept behind a symlink is pruned too.
    Call it only inside `locked`, after this run took the entry at `backup` out. It never raises and prints nothing.
    """
    place = backup_place(state, backup)
    if place is not None:
        empty_out(state, *place)


def empty_out(state, stamp, harness=None):
    """Remove <state>/backups/<stamp>/<harness> if `harness` is given and it is empty, then <stamp> if it is empty.

    The first rmdir that fails ends it. It never follows a symlink at backups/ or <stamp>.
    Call it only inside `locked`. It never raises and prints nothing.
    """
    if os.rmdir not in os.supports_dir_fd:
        return
    # O_NOFOLLOW refuses a symlink at backups/ or <stamp>, and rmdir refuses a symlink, a file, and a directory that holds anything.
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    with suppress(OSError):
        top = os.open(os.path.join(str(state), "backups"), flags)
        try:
            inner = os.open(stamp, flags, dir_fd=top)
            try:
                if harness is not None:
                    os.rmdir(harness, dir_fd=inner)
            finally:
                os.close(inner)
            os.rmdir(stamp, dir_fd=top)
        finally:
            os.close(top)


def settle(strays, state, root, dry_run):
    """Act on each Stray and print one line for each that held an entry. Without `dry_run`, call it only inside `locked`.

    Every move is `place`, so nothing is overwritten. Only a second name and this checkout's own link are ever deleted,
    and a holder is removed only once it is empty. With `dry_run` it prints what it would do and changes nothing.
    """
    recovered, removed = ("would recover", "would remove") if dry_run else ("recovered", "removed")
    dropped = []
    for stray in strays:
        try:
            if stray.kind == "empty":
                if not dry_run:
                    with suppress(OSError):
                        os.rmdir(stray.path)
            elif stray.kind == "left":
                print(f"left {stray.path}: {stray.why}")
            elif stray.kind == "home":
                reason = None if dry_run else put_back(stray.path, stray.home)
                if reason is None:
                    print(f"{recovered} {stray.home} from {stray.path}")
                else:
                    print(f"left {stray.path}: {reason}")
            elif stray.kind == "spare":
                if not dry_run:
                    if not one_entry(stray.path, stray.twin):
                        print(f"left {stray.path}: it is no longer a second name for {stray.twin}")
                        continue
                    os.unlink(stray.path)
                    if stray.drop:
                        patch_legacy(state, (), (), (), (stray.drop,), False)
                        dropped.append(stray.drop)
                print(f"{removed} {stray.path}: it was a second name for {stray.twin}")
            elif stray.kind == "own":
                if not dry_run:
                    if not proves(root, stray.path, stray.home):
                        print(f"left {stray.path}: it is no longer this checkout's link")
                        continue
                    os.unlink(stray.path)
                print(f"{removed} {stray.path}: it is this checkout's link and {stray.home} is taken")
        except OSError as error:
            print(f"left {stray.path}: {error}")
    if not dry_run:
        for holder in sorted({os.path.dirname(stray.path) for stray in strays if stray.kind != "empty"}):
            # rmdir refuses a directory that is not empty, so an entry that was left stays.
            with suppress(OSError):
                os.rmdir(holder)
        for backup in dropped:
            prune(state, backup)


def buried(state, root, path):
    """Whether a backup row now holds this checkout's entry for the slot of `path`."""
    file = Path(state) / LEGACY_NAME
    if not file.exists():
        return False
    _data, _links, backups = legacy_lists(file)
    return any(
        isinstance(row, dict) and isinstance(row.get("original"), str) and isinstance(row.get("backup"), str)
        and slot_of(row["original"]) == slot_of(path) and proves(root, row["backup"], row["original"])
        for row in backups
    )


def act(step, root):
    """Do the step's change. Return why it was not done when it declined without an error."""
    if step.kind == "create":
        os.makedirs(os.path.dirname(step.path), exist_ok=True)
        os.symlink(link_target(root, step.path), step.path, target_is_directory=True)
    elif step.kind == "move":
        shutil.move(step.path, step.backup)
    elif step.kind == "unlink":
        return remove_link(step.path, root, step.path, "link")
    elif step.kind == "withdraw":
        return remove_link(step.backup, root, step.path, "backup")
    elif step.kind == "restore":
        os.makedirs(os.path.dirname(step.path), exist_ok=True)
        return restore_backup(step.backup, step.path, step.held)


def execute(plan, state, root):
    counts = {"linked": 0, "removed": 0, "restored": 0, "withdrawn": 0, "kept_extra": 0, "skipped": 0}
    failed = set()
    stamp = None
    made = []
    try:
        for step in plan.steps:
            if step.kind == "move":
                if stamp is None:
                    backups = Path(state) / "backups"
                    backups.mkdir(parents=True, exist_ok=True)
                    stamp = tempfile.mkdtemp(prefix=f"{time.strftime('%Y%m%dT%H%M%S')}-{os.getpid()}-", dir=backups)
                backup = os.path.join(stamp, step.place)
                step = replace(step, backup=backup, add_backups=({"harnesses": list(step.harnesses), "original": step.path, "backup": backup},))
            # A backup row that holds this checkout's entry needs the claim to stay owned after it is restored.
            if step.kind == "forget" and (step.path in failed or buried(state, root, step.path)):
                counts["kept_extra"] += len(step.remove_claims)
                continue
            if not ready(step, root):
                note = skip_note(step)
                if note:
                    print(note)
                    counts["skipped"] += 1
                failed.add(step.path)
                continue
            undo = add_records(step, state, root)
            try:
                if step.kind == "move":
                    harness = os.path.basename(os.path.dirname(step.backup))
                    if harness not in made:
                        # mkdir refuses a <harness> that is already there, so this run never uses one it did not make.
                        os.mkdir(os.path.dirname(step.backup))
                        made.append(harness)
                declined = act(step, root)
            except OSError as error:
                # A move can fail after copying part of the entry, and then the row is the only record of that copy.
                if not (step.kind == "move" and os.path.lexists(step.backup)):
                    undo()
                print(f"skipped {subject(step)}: {error}")
                counts["skipped"] += 1
                failed.add(step.path)
                continue
            if declined:
                undo()
                print(f"skipped {subject(step)}: {declined}")
                counts["skipped"] += 1
                failed.add(step.path)
                continue
            remove_records(step, state, root)
            for backup in step.remove_backups:
                prune(state, backup)
            if step.kind == "create":
                counts["linked"] += 1
            elif step.kind == "unlink":
                counts["removed"] += 1
            elif step.kind == "withdraw":
                counts["removed"] += 1
                counts["withdrawn"] += 1
            elif step.kind == "restore":
                counts["restored"] += 1
    finally:
        if stamp is not None:
            name = os.path.basename(stamp)
            for harness in made:
                empty_out(state, name, harness)
            empty_out(state, name)
    return counts


@contextmanager
def locked(state):
    state = Path(state)
    state.mkdir(parents=True, exist_ok=True)
    fd = os.open(state, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def needs_lock(plan, strays, state):
    writes = bool(plan.steps) or any(stray.kind != "left" for stray in strays)
    another_run_can_hold_it = os.path.isdir(state)
    return writes or (bool(strays) and another_run_can_hold_it)


def count_steps(plan, kind):
    kinds = {kind} if isinstance(kind, str) else set(kind)
    return sum(1 for step in plan.steps if step.kind in kinds)


def report_install(plan, state, root, executed, dry_run):
    for line in plan.refusals:
        print(line)
    if dry_run:
        moved = {step.path for step in plan.steps if step.kind == "move"}
        for step in plan.steps:
            if step.kind != "create":
                continue
            suffix = f" (replacing {describe(step.path)})" if step.path in moved else ""
            print(f"would link {step.path} -> {link_target(root, step.path)}{suffix}")
        if plan.untracked:
            print(f"{plan.untracked} links already point at this checkout but are not tracked; uninstall leaves them")
        if plan.adopted:
            print(f"adopted {plan.adopted} links an older installer recorded")
        print(f"{count_steps(plan, 'create')} links planned")
        return
    linked = 0 if executed is None else executed["linked"]
    joined = ", ".join(sorted({harness for step in plan.steps if step.kind == "create" for harness in step.harnesses}))
    print(f"linked {linked} skills into {joined or 'nothing (already installed)'}")
    if plan.untracked:
        print(f"{plan.untracked} links already point at this checkout but are not tracked; uninstall leaves them")
    if plan.adopted:
        print(f"adopted {plan.adopted} links an older installer recorded")
    print(f"manifest: {Path(state) / LEGACY_NAME}")


def report_uninstall(plan, executed, dry_run):
    for line in plan.occupied:
        print(line)
    if dry_run:
        removed = count_steps(plan, ("unlink", "withdraw"))
        restored = count_steps(plan, "restore")
        withdrawn = count_steps(plan, "withdraw")
        print(f"would remove {removed} links, would restore {restored} entries")
    else:
        removed = 0 if executed is None else executed["removed"]
        restored = 0 if executed is None else executed["restored"]
        withdrawn = 0 if executed is None else executed["withdrawn"]
        print(f"removed {removed} links, restored {restored} entries")
    if withdrawn:
        print(f"{withdrawn} of them had been moved aside by another checkout's --replace")
    for others in plan.shared:
        print(f"kept entries whose directory is shared with {others}; select those harnesses too to remove them")
    kept = plan.kept + (0 if executed is None else executed["kept_extra"])
    if kept:
        print(f"kept {kept} records whose links no longer point at this checkout; they apply again if the links come back")


def skill_names():
    return sorted(path.name for path in SKILLS.iterdir() if (path / "SKILL.md").is_file())


def install(args):
    if not SKILLS.is_dir():
        sys.exit("skills/ is missing; run python3 scripts/build.py first")
    user = args.project is None
    scope = Path(args.project).resolve() if args.project else None
    root = str(ROOT)
    state = state_dir(scope, user)
    names = skill_names()

    def make_plan(view):
        return plan_install(view, scope, user, args.harness, names, root, args.replace)

    def reject(plan):
        if plan.conflicts and not args.replace:
            for line in plan.refusals:
                print(line)
            lines = [f"  {'/'.join(harnesses)}: {path} ({describe(path)})" for harnesses, path in plan.conflicts]
            sys.exit("these skills already exist; rerun with --replace to move them aside (uninstall restores them):\n" + "\n".join(lines))

    def strays(view):
        return survey(view, scope, user, state, root, args.harness)

    view = load(scope, user)
    plan = make_plan(view)
    found = strays(view)
    if plan.conflicts and not args.replace:
        settle(tuple(stray for stray in found if stray.kind == "left"), state, root, True)
    reject(plan)
    if args.dry_run or not needs_lock(plan, found, state):
        settle(found, state, root, True)
        report_install(plan, state, root, None, args.dry_run)
        return 0
    with locked(state):
        settle(strays(load(scope, user)), state, root, False)
        plan = make_plan(load(scope, user))
        reject(plan)
        executed = execute(plan, state, root) if plan.steps else None
        report_install(plan, state, root, executed, False)
    return SKIPPED if executed and executed["skipped"] else 0


def uninstall(args):
    user = args.project is None
    scope = Path(args.project).resolve() if args.project else None
    root = str(ROOT)
    state = state_dir(scope, user)

    def make_plan(view, holds):
        return plan_uninstall(view, root, args.harness, holds)

    def strays(view):
        return survey(view, scope, user, state, root, args.harness)

    view = load(scope, user)
    with ExitStack() as holds:
        plan = make_plan(view, holds)
    found = strays(view)
    if args.dry_run or not needs_lock(plan, found, state):
        settle(found, state, root, True)
        report_uninstall(plan, None, args.dry_run)
        return 0
    with locked(state), ExitStack() as holds:
        settle(strays(load(scope, user)), state, root, False)
        plan = make_plan(load(scope, user), holds)
        executed = execute(plan, state, root) if plan.steps else None
        report_uninstall(plan, executed, False)
    return SKIPPED if executed and executed["skipped"] else 0


def points_here(path):
    return proves(str(ROOT), os.fspath(path), os.fspath(path))


@dataclass(frozen=True)
class Finding:
    """One record that no longer matches the disk.

    `line` is the whole sentence doctor prints when the record is alone in its head, advice included.
    `head` is the sentence doctor prints once over every record with the same `head`, without its leading count.
    `item` is this record's line under that head. A finding with an empty `head` is never grouped.
    `harnesses` are the harnesses it prints under. A finding with none prints after the last harness.
    """
    harnesses: tuple
    line: str
    head: str = ""
    item: str = ""


@dataclass(frozen=True)
class Unread:
    """One record file doctor could not use. `line` names the file and says what doctor did not check.

    `blinds` is true for the manifest and for this checkout's owner file, the two files install and uninstall stop on.
    """
    line: str
    blinds: bool


@dataclass(frozen=True)
class Audit:
    """What doctor found in the records. `findings` are Findings and `unread` are Unreads."""
    findings: tuple
    unread: tuple


RELINK = ('claim {path}: nothing is there; run "{install}" to link it again, '
          'then "{uninstall}" removes the link and this claim')
RELINK_MANY = ('claims have nothing at their paths; run "{install}" to link them again, '
               'then "{uninstall}" removes the links and these claims:')
REPLACE = ('claim {path}: {there}; "{install}" stops on {n} taken paths; with --replace it moves them aside '
           'and links this path (uninstall restores them and removes this claim)')
REPLACE_MANY = ('claims; "{install}" stops on {n} taken paths; with --replace it moves them aside '
                'and links the path of each claim (uninstall restores them and removes these claims):')
EDIT = ('claim {path}: {there}; install plans no link at that path, so no command clears this claim; '
        'to drop it, delete the "{path}" entry from {owner_file}')
EDIT_MANY = ('claims; install plans no link at the path of any of them, so no command clears them; '
             'to drop one, delete the entry named by its path from {owner_file}:')
UNBUILT = ('claim {path}: {there}; skills/ is missing, so install stops before it plans a link; '
           'run python3 scripts/build.py first and rerun doctor')
UNBUILT_MANY = ('claims; skills/ is missing, so install stops before it plans a link; '
                'run python3 scripts/build.py first and rerun doctor:')
HELD_CLAIM = ('claim {path}: {there}, and {aside} holds this checkout\'s link for it; '
              '"{dry_run}" prints what the next run does with it')
HELD_MANY = 'records; "{dry_run}" prints what the next run does with the entry held for each:'
INERT_ROW = ('backup row {backup}: nothing is there (recorded as the backup of {original}); uninstall skips the row '
             'while that path is empty; to drop it, delete the row from "backups" in {manifest}')
INERT_ROW_MANY = ('backup rows have nothing at their backup paths; uninstall skips each row while its backup path is empty; '
                  'to drop one, delete the row from "backups" in {manifest}:')
HELD_ROW = ('backup row {backup}: nothing is there, and {aside} holds an entry under that name; '
            '"{dry_run}" prints what the next run does with it')
AWAY = ('{file}: claims {n} links here for checkout {checkout}, and no directory is at {checkout}; '
        'delete this file unless that checkout will be back at that path; deleting it removes that checkout\'s claims '
        'and removes no link they name and no row of {manifest}')


def command(args, *words):
    """One shell command for a person to copy and run from this checkout. Every argument is quoted for a POSIX shell."""
    project = (f"--project={args.project}",) if args.project else ()
    return shlex.join(("python3", "scripts/install.py", *words, *project))


def claim_finding(args, view, scope, user, names, root, path, harnesses, aside):
    """The Finding for one stale claim. The advice comes from what `plan_install` plans for the path right now."""
    there = f"a {describe(path)} is there" if os.path.lexists(path) else "nothing is there"
    if aside:
        dry_run = command(args, "uninstall", "--dry-run")
        return Finding(harnesses, HELD_CLAIM.format(path=path, there=there, aside=aside, dry_run=dry_run),
                       HELD_MANY.format(dry_run=dry_run), f"claim {path}: {there}, and {aside} holds this checkout's link for it")
    if not SKILLS.is_dir():
        return Finding(harnesses, UNBUILT.format(path=path, there=there), UNBUILT_MANY, f"{path}: {there}")
    plain = plan_install(view, scope, user, harnesses, names, root, replace=False)
    forced = plan_install(view, scope, user, harnesses, names, root, replace=True)

    def links(plan):
        return any(step.kind == "create" and slot_of(step.path) == slot_of(path) for step in plan.steps)

    install = command(args, "install", "--harness", ",".join(harnesses))
    if links(plain) and not plain.conflicts:
        uninstall = command(args, "uninstall", "--harness", ",".join(harnesses))
        return Finding(harnesses, RELINK.format(path=path, install=install, uninstall=uninstall),
                       RELINK_MANY.format(install=install, uninstall=uninstall), path)
    if links(forced):
        n = len(plain.conflicts)
        return Finding(harnesses, REPLACE.format(path=path, there=there, install=install, n=n),
                       REPLACE_MANY.format(install=install, n=n), f"{path}: {there}")
    owner_file = owner_path(state_dir(scope, user), root)
    return Finding(harnesses, EDIT.format(path=path, there=there, owner_file=owner_file),
                   EDIT_MANY.format(owner_file=owner_file), f"{path}: {there}")


def row_finding(args, state, row, aside):
    """The Finding for one backup row with nothing at its backup path."""
    if aside:
        dry_run = command(args, "uninstall", "--dry-run")
        return Finding(row.harnesses, HELD_ROW.format(backup=row.backup, aside=aside, dry_run=dry_run),
                       HELD_MANY.format(dry_run=dry_run),
                       f"backup row {row.backup}: nothing is there, and {aside} holds an entry under that name")
    manifest = Path(state) / LEGACY_NAME
    return Finding(row.harnesses, INERT_ROW.format(backup=row.backup, original=row.original, manifest=manifest),
                   INERT_ROW_MANY.format(manifest=manifest), f"{row.backup} (recorded as the backup of {row.original})")


def grouped(findings):
    """The lines doctor prints for `findings`.

    Findings with the same non-empty `head` print as one group at the position of the first of them: the count and
    the head, then the `item` of each, two columns deeper. A finding alone in its head prints its `line`.
    """
    groups = {}
    for index, finding in enumerate(findings):
        groups.setdefault(finding.head or index, []).append(finding)
    lines = []
    for head, members in groups.items():
        if len(members) == 1:
            lines.append(members[0].line)
        else:
            lines.append(f"{len(members)} {head}")
            lines.extend(f"  {member.item}" for member in members)
    return lines


def audit(args, scope, user, names):
    """Read the records and return an Audit. Reads only: no lock, no directory made, no file written."""
    state, root = state_dir(scope, user), str(ROOT)
    stale, away, unread = [], [], []
    mine = owner_path(state, root)
    for name in listing(state / OWNERS_DIR):
        file = state / OWNERS_DIR / name
        if not name.endswith(".json") or file == mine:
            continue
        try:
            data = read_object(file)
        except (Unreadable, OSError) as error:
            unread.append(Unread(f"{error} (doctor read no checkout from it)", False))
            continue
        checkout = data.get("checkout")
        if not isinstance(checkout, str):
            unread.append(Unread(f"{file} names no checkout (doctor read no checkout from it)", False))
            continue
        if os.path.isdir(checkout):
            continue
        claimed = claims_in(data)
        for harness in HARNESSES:
            count = sum(1 for harnesses in claimed.values() if harness in harnesses)
            if count:
                away.append(Finding((harness,), AWAY.format(file=file, n=count, checkout=checkout, manifest=state / LEGACY_NAME)))
    try:
        manifest = read_legacy(state, scope, user)
    except (Unreadable, OSError) as error:
        manifest = None
        unread.append(Unread(f"{error} (doctor checked no claims and no backup rows)", True))
    try:
        claims = current_claims(state, root)
    except (Unreadable, OSError) as error:
        claims = {}
        unread.append(Unread(f"{error} (doctor checked no claims of this checkout)", True))
    if manifest is None:
        return Audit(tuple(away), tuple(unread))
    view = View(claims, *manifest)
    strays = survey(view, scope, user, state, root, HARNESSES)
    present = stacks(view)
    for path, harnesses in claims.items():
        if proves(root, path, path) or set_aside(present, root, slot_of(path)):
            continue
        aside = next((stray.path for stray in strays
                      if stray.kind in ("home", "own") and slot_of(stray.home) == slot_of(path)), None)
        stale.append(claim_finding(args, view, scope, user, names, root, path, harnesses, aside))
    held_for = {stray.home: stray.path for stray in strays if stray.kind != "empty"}
    for row in view.backups:
        if not os.path.lexists(row.backup):
            stale.append(row_finding(args, state, row, held_for.get(row.backup)))
    return Audit(tuple(stale + away), tuple(unread))


def link_health(harness, directory, names, scope, user):
    """Print what `harness` loads from `directory`. Return whether it loads every skill of this checkout."""
    if Path(os.path.realpath(directory)) == Path(os.path.realpath(SKILLS)):
        print(f"{harness:7} {directory}: resolves to the pstack-t3 skills tree itself")
        return True
    if inside_checkout(directory):
        print(f"{harness:7} {directory}: points inside one pstack-t3 skill, so the other skills are invisible")
        return False
    installed = [name for name in names if points_here(directory / name)]
    foreign = [name for name in names if (directory / name).exists() and not points_here(directory / name)]
    missing = [name for name in names if not (directory / name).exists()]
    healthy = not foreign and not missing
    print(f"{harness:7} {directory}: {len(installed)}/{len(names)} pstack-t3" +
          (f", {len(foreign)} taken by other copies ({', '.join(foreign[:5])}{'...' if len(foreign) > 5 else ''})" if foreign else "") +
          (f", {len(missing)} missing" if missing else ""))
    for extra in extra_dirs(scope, user)[harness]:
        stale = [name for name in names if (extra / name).exists() and not points_here(extra / name)]
        if stale:
            healthy = False
            print(f"        {extra} also holds other copies of {len(stale)} of these "
                  f"({', '.join(stale[:5])}{'...' if len(stale) > 5 else ''}); {harness} may load those instead")
    if not user:
        # Claude and Grok load the user copy when both scopes define a name.
        user_directory = skill_dirs(None, True)[harness]
        shadowing = [name for name in installed if (user_directory / name).exists() and not points_here(user_directory / name)]
        if shadowing:
            healthy = False
            print(f"        user scope {user_directory} has other copies of {len(shadowing)} of these "
                  f"({', '.join(shadowing[:5])}{'...' if len(shadowing) > 5 else ''}); providers that prefer user scope will load those instead")
    return healthy


def doctor(args):
    user = args.project is None
    scope = Path(args.project).resolve() if args.project else None
    names = skill_names() if SKILLS.is_dir() else []
    found = audit(args, scope, user, names)
    healthy = True
    for harness, directory in skill_dirs(scope, user).items():
        if harness not in args.harness:
            continue
        healthy &= link_health(harness, directory, names, scope, user)
        for line in grouped([finding for finding in found.findings if harness in finding.harnesses]):
            print(f"        {line}")
    for line in grouped([finding for finding in found.findings if not finding.harnesses]):
        print(line)
    for item in found.unread:
        print(item.line)
    return 0 if healthy and not any(item.blinds for item in found.unread) else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("install", "uninstall", "doctor"), nargs="?", default="install")
    parser.add_argument("--project", help="install into this repository instead of the user's skill directories")
    parser.add_argument("--harness", default="all", help="comma list of " + ",".join(HARNESSES) + ", or all")
    parser.add_argument("--replace", action="store_true", help="move conflicting skills aside; uninstall restores them")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    args.harness = HARNESSES if args.harness == "all" else tuple(item.strip() for item in args.harness.split(","))
    unknown = set(args.harness) - set(HARNESSES)
    if unknown:
        parser.error(f"unknown harness {', '.join(sorted(unknown))}")
    try:
        return {"install": install, "uninstall": uninstall, "doctor": doctor}[args.command](args) or 0
    except Unreadable as error:
        sys.exit(str(error))


if __name__ == "__main__":
    sys.exit(main())
