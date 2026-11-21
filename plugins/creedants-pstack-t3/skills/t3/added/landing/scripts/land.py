#!/usr/bin/env python3
"""Land many agents' work on one repository through one queue.

Each repository (one git common directory) gets a contract, a lease table
that keeps writers off each other's paths, and a queue that is the only
writer to trunk. The queue is a lock, not a process: whoever runs `land`
while holding it drains the queue. State lives in SQLite so every change is
one transaction. Heavy commands take a slot from a machine-wide governor.
"""

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import posixpath
import re
import signal
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

MODES = ("human", "merge", "push", "local")
LEGACY_MODES = {"auto": "push"}
REMOTE_MODES = ("human", "merge", "push")
MERGE_METHODS = ("merge", "squash", "rebase")
MERGE_FLAGS = {
    "merge": "mergeCommitAllowed",
    "squash": "squashMergeAllowed",
    "rebase": "rebaseMergeAllowed",
}
# GitHub's mergePullRequest error names the method in this sentence.
METHOD_REFUSAL = (
    ("merge", "Merge commits are not allowed on this repository"),
    ("squash", "Squash merges are not allowed on this repository"),
    ("rebase", "Rebase merges are not allowed on this repository"),
)
SCHEMA = """
CREATE TABLE IF NOT EXISTS contract (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS lease (
  id INTEGER PRIMARY KEY, at TEXT NOT NULL, holder TEXT NOT NULL, paths TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('active', 'submitted', 'released')), expires TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS entry (
  id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, holder TEXT NOT NULL, branch TEXT NOT NULL,
  sha TEXT NOT NULL, base TEXT NOT NULL, fingerprint TEXT NOT NULL, lease INTEGER NOT NULL REFERENCES lease(id),
  reviewer TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('queued', 'landing', 'awaiting-merge', 'landed', 'bounced')),
  candidate TEXT NOT NULL DEFAULT '', landed TEXT NOT NULL DEFAULT '', pr TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT '', UNIQUE (sha, holder));
CREATE TABLE IF NOT EXISTS attempt (
  id INTEGER PRIMARY KEY, at TEXT NOT NULL, base TEXT NOT NULL, candidate TEXT NOT NULL,
  entries TEXT NOT NULL, state TEXT NOT NULL CHECK (state IN ('publishing', 'published', 'abandoned')));
CREATE TABLE IF NOT EXISTS log (at TEXT NOT NULL, kind TEXT NOT NULL, id INTEGER NOT NULL, state TEXT NOT NULL, note TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS owner (prefix TEXT PRIMARY KEY, generation INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS reservation (
  id INTEGER PRIMARY KEY, at TEXT NOT NULL, prefix TEXT NOT NULL, paths TEXT NOT NULL,
  ruling TEXT NOT NULL UNIQUE, ttl REAL NOT NULL, armed TEXT NOT NULL DEFAULT '', expires TEXT NOT NULL DEFAULT '',
  taken TEXT NOT NULL DEFAULT '', state TEXT NOT NULL CHECK (state IN ('standing', 'claimed', 'lifted')));
CREATE TABLE IF NOT EXISTS share (prefix TEXT PRIMARY KEY, count INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS contest (
  id INTEGER PRIMARY KEY, at TEXT NOT NULL, a TEXT NOT NULL, b TEXT NOT NULL, first TEXT NOT NULL DEFAULT '',
  state TEXT NOT NULL CHECK (state IN ('open', 'settled', 'cancelled')));
"""


class LandError(Exception):
    pass


def now():
    return datetime.now(timezone.utc)


def stamp(moment=None):
    return (moment or now()).isoformat(timespec="microseconds")


def state_home():
    return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "pstack-t3"


def git(*args, cwd, check=True, stdin=None):
    """Run git with LC_ALL=C. Callers parse English diagnostics such as CONFLICT."""
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    result = subprocess.run(["git", *args], cwd=cwd, input=stdin, capture_output=True, text=True,
                            encoding="utf-8", errors="surrogateescape", env=env)
    if check and result.returncode != 0:
        raise LandError(f"git {' '.join(args)} failed: {(result.stderr or result.stdout).strip()}")
    return result


def git_push(*args, cwd, check=False):
    """Every queue push passes --no-follow-tags, so push.followTags cannot publish a local tag."""
    return git("push", "--no-follow-tags", *args, cwd=cwd, check=check)


def common_dir(path):
    """The git common directory identifies a repository across all of its worktrees."""
    top = git("rev-parse", "--show-toplevel", cwd=path).stdout.strip()
    return Path(git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=top).stdout.strip()).resolve()


def canonical(path, kind="lease"):
    """Repository-relative POSIX path with no aliases. An empty string is the whole repository."""
    value = posixpath.normpath(path.strip().replace("\\", "/")).lstrip("/")
    if value in (".", ""):
        return ""
    if value == ".." or value.startswith("../"):
        raise LandError(f"{kind} path {path!r} leaves the repository")
    return value


def overlaps(first, second):
    return any(a == "" or b == "" or a == b or a.startswith(b + "/") or b.startswith(a + "/") for a in first for b in second)


def covered(path, paths):
    return any(p == "" or path == p or path.startswith(p + "/") for p in paths)


def fingerprint(repo, base, head):
    """Hash of the change itself: content, whitespace, modes, and binaries, without line numbers or blob IDs."""
    diff = git("diff", "--binary", "--full-index", "--no-renames", "--no-textconv", "--no-ext-diff", "-U0", base, head, cwd=repo).stdout
    lines = [line for line in diff.splitlines() if not line.startswith("index ")]
    lines = [re.sub(r"^@@ [^@]* @@", "@@", line) for line in lines]
    return hashlib.sha256("\n".join(lines).encode("utf-8", "surrogateescape")).hexdigest() if diff else ""


def changed_paths(repo, base, head):
    return [p for p in git("diff", "-z", "--name-only", "--no-renames", base, head, cwd=repo).stdout.split("\0") if p]


# Governor


def governor_dir():
    return state_home() / "governor"


def governor_slots():
    config = governor_dir() / "governor.json"
    if config.exists():
        return max(1, int(json.loads(config.read_text()).get("slots", 1)))
    return max(1, min(4, (os.cpu_count() or 4) // 4))


@contextlib.contextmanager
def exclusive_slot():
    """Hold every slot, landing included, so a benchmark runs on a quiet machine.
    Slots are taken in a fixed order with blocking locks, so two exclusive callers cannot deadlock."""
    if os.environ.get("LAND_SLOT"):
        raise LandError("an exclusive slot must be the outermost slot; this command already runs inside one")
    directory = governor_dir()
    directory.mkdir(parents=True, exist_ok=True)
    names = ["landing-0"] + [f"worker-{index}" for index in range(governor_slots())]
    handles = [open(directory / name, "a") for name in names]
    try:
        for handle in handles:
            fcntl.flock(handle, fcntl.LOCK_EX)
        os.environ["LAND_SLOT"] = "exclusive"
        yield
    finally:
        os.environ.pop("LAND_SLOT", None)
        for handle in handles:
            handle.close()


@contextlib.contextmanager
def slot(pool="worker"):
    """Hold one slot of a pool. Landing checks use their own one-slot pool so workers never starve the queue.
    A command already inside a slot (LAND_SLOT set) runs without taking another, so nesting cannot deadlock."""
    if os.environ.get("LAND_SLOT"):
        yield
        return
    directory = governor_dir()
    directory.mkdir(parents=True, exist_ok=True)
    count = 1 if pool == "landing" else governor_slots()
    handles = [open(directory / f"{pool}-{index}", "a") for index in range(count)]
    held = None
    try:
        while held is None:
            for handle in handles:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    held = handle
                    break
                except BlockingIOError:
                    continue
            if held is None:
                time.sleep(0.5)
        os.environ["LAND_SLOT"] = pool
        yield
    finally:
        os.environ.pop("LAND_SLOT", None)
        for handle in handles:
            handle.close()


def supervised(command, cwd, timeout):
    """Run a shell command in its own process group and kill the whole group on timeout."""
    process = subprocess.Popen(command, cwd=cwd, shell=True, start_new_session=True,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        output, _ = process.communicate(timeout=timeout)
        return process.returncode, output.decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        try:
            output, _ = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            # A descendant left the group with setsid and still holds the pipe. Stop waiting for it.
            process.stdout.close()
            process.wait()
            output = b""
        return None, output.decode("utf-8", "replace")


# Store


class Store:
    def __init__(self, directory):
        self.dir = Path(directory)
        self.db = sqlite3.connect(self.dir / "land.db", timeout=60, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)
        columns = {row["name"] for row in self.db.execute("PRAGMA table_info(entry)")}
        for column in ("title", "body"):
            if column not in columns:
                self.db.execute(f"ALTER TABLE entry ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
        migrate_entry_ids(self.db)

    @classmethod
    def for_repo(cls, path):
        common = common_dir(path)
        directory = state_home() / "landing" / store_name(common)
        if not (directory / "land.db").exists():
            raise LandError(f"{common.parent} has no landing contract; run land.py init in it")
        store = cls(directory)
        if Path(store.contract["commonDir"]) != common:
            raise LandError(f"store {directory} belongs to {store.contract['commonDir']}, not {common}")
        return store

    @contextlib.contextmanager
    def tx(self):
        """One short write transaction. Never run git or checks inside it."""
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield self.db
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    @contextlib.contextmanager
    def trial(self):
        """One transaction that sees its own writes and keeps none of them."""
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield self.db
        finally:
            self.db.execute("ROLLBACK")

    @property
    def contract(self):
        contract = {row["key"]: json.loads(row["value"]) for row in self.db.execute("SELECT key, value FROM contract")}
        if "mode" in contract:
            contract["mode"] = LEGACY_MODES.get(contract["mode"], contract["mode"])
        return contract

    @property
    def repo(self):
        return Path(self.contract["repo"])

    def log(self, db, kind, ident, state, note=""):
        db.execute("INSERT INTO log VALUES (?, ?, ?, ?, ?)", (stamp(), kind, ident, state, note))

    def set_entry(self, db, ident, state, **fields):
        assignments = ", ".join(f"{key} = ?" for key in ["state", *fields])
        db.execute(f"UPDATE entry SET {assignments} WHERE id = ?", (state, *fields.values(), ident))
        self.log(db, "entry", ident, state, fields.get("note", ""))

    def entries(self, *states):
        marks = ",".join("?" * len(states))
        return list(self.db.execute(f"SELECT * FROM entry WHERE state IN ({marks}) ORDER BY id", states))


def migrate_entry_ids(db):
    """Copy an older entry table so ids are never reused after a bounced row is deleted.

    SQLite reuses the largest rowid once that row is gone, and a resubmit deletes
    the bounced row. AUTOINCREMENT can only be declared in CREATE TABLE. The copy
    keeps every existing id. sqlite_sequence is renamed with the table so the next
    id is one past the highest id the table has held.
    """
    row = db.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'entry'").fetchone()
    if row is None or "AUTOINCREMENT" in row["sql"].upper():
        return
    columns = [info["name"] for info in db.execute("PRAGMA table_info(entry)")]
    db.execute("PRAGMA foreign_keys=OFF")
    db.execute("BEGIN")
    try:
        db.execute("""
            CREATE TABLE entry_id_keep (
              id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, holder TEXT NOT NULL, branch TEXT NOT NULL,
              sha TEXT NOT NULL, base TEXT NOT NULL, fingerprint TEXT NOT NULL, lease INTEGER NOT NULL REFERENCES lease(id),
              reviewer TEXT NOT NULL,
              state TEXT NOT NULL CHECK (state IN ('queued', 'landing', 'awaiting-merge', 'landed', 'bounced')),
              candidate TEXT NOT NULL DEFAULT '', landed TEXT NOT NULL DEFAULT '', pr TEXT NOT NULL DEFAULT '',
              note TEXT NOT NULL DEFAULT '', title TEXT NOT NULL DEFAULT '', body TEXT NOT NULL DEFAULT '',
              UNIQUE (sha, holder))
        """)
        names = ", ".join(columns)
        db.execute(f"INSERT INTO entry_id_keep ({names}) SELECT {names} FROM entry")
        db.execute("DROP TABLE entry")
        db.execute("ALTER TABLE entry_id_keep RENAME TO entry")
        if db.execute("SELECT 1 FROM sqlite_master WHERE name = 'sqlite_sequence'").fetchone():
            db.execute("UPDATE sqlite_sequence SET name = 'entry' WHERE name = 'entry_id_keep'")
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        raise


def store_name(common):
    name = common.parent.name if common.name == ".git" else common.name.removesuffix(".git")
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") + "-" + hashlib.sha1(str(common).encode()).hexdigest()[:8]


def pin_ref(sha):
    return f"refs/landing/pins/{sha}"


def committer(repo):
    """Cherry-picks need a committer. Use the repository's identity, or a fixed one when it has none."""
    if git("config", "user.email", cwd=repo, check=False).stdout.strip():
        return []
    return ["-c", "user.name=pstack landing", "-c", "user.email=landing@localhost"]


def git_reason(stderr):
    """The useful line of a git failure: what the remote said, else the last line."""
    lines = [line.strip() for line in stderr.strip().splitlines() if line.strip()]
    remote = [line for line in lines if line.startswith("remote:") and line != "remote:"]
    return " ".join(remote) if remote else (lines[-1] if lines else "no output")


class Infrastructure(LandError):
    """A failure that is not the entry's fault. The queue pauses instead of bouncing."""


class AutoMergeStillEnabled(Infrastructure):
    """The message is the whole pause. land() stores it unchanged."""


def trunk_ref(contract):
    if contract["mode"] == "local":
        return f"refs/landing/{contract['trunk']}"
    return f"refs/remotes/{contract['remote']}/{contract['trunk']}"


def allowed_merge_methods(repo):
    """The methods gh says this repository allows, or None when gh cannot say."""
    fields = ",".join(MERGE_FLAGS[method] for method in MERGE_METHODS)
    try:
        result = gh("repo", "view", "--json", fields, cwd=repo)
    except OSError:
        return None
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout or "")
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    allowed = []
    for method in MERGE_METHODS:
        flag = payload.get(MERGE_FLAGS[method])
        if not isinstance(flag, bool):
            return None
        if flag:
            allowed.append(method)
    return tuple(allowed)


def allowed_list(allowed):
    return ", ".join(allowed) if allowed else "none"


def pick_merge_method(explicit, allowed):
    """The method init stores. When gh cannot say, an omitted method stays merge."""
    if allowed is None:
        return explicit or "merge"
    if explicit:
        if explicit not in allowed:
            raise LandError(f"repository does not allow {explicit}; allowed: {allowed_list(allowed)}")
        return explicit
    if len(allowed) == 1:
        return allowed[0]
    if "merge" in allowed:
        return "merge"
    if "squash" in allowed:
        return "squash"
    raise LandError(f"repository allows no merge method; allowed: {allowed_list(allowed)}")


def refused_merge_method(text):
    for method, phrase in METHOD_REFUSAL:
        if phrase in (text or ""):
            return method
    return None


def suggested_merge_method(repo, problem):
    """An allowed method other than the one GitHub just refused, preferring squash."""
    refused = refused_merge_method(problem)
    if not refused:
        return None
    allowed = allowed_merge_methods(repo)
    if not allowed:
        return None
    for method in ("squash", "rebase", "merge"):
        if method in allowed and method != refused:
            return method
    return None


def busy_queue_message(count):
    noun = "entry is" if count == 1 else "entries are"
    return f"{count} {noun} queued, landing, or awaiting merge; change the mode when the queue is empty"


def init(path, trunk, mode, remote, base, checks, setup, batch, timeout, merge_method=None, cap=None):
    mode = LEGACY_MODES.get(mode, mode)
    common = common_dir(path)
    repo = common.parent if common.name == ".git" else Path(git("rev-parse", "--show-toplevel", cwd=path).stdout.strip())
    directory = state_home() / "landing" / store_name(common)
    directory.mkdir(parents=True, exist_ok=True)
    if mode == "merge" or merge_method:
        merge_method = pick_merge_method(merge_method, allowed_merge_methods(repo))
    else:
        merge_method = "merge"
    store = Store(directory)
    wanted = {"commonDir": str(common), "repo": str(repo), "trunk": trunk, "mode": mode, "remote": remote,
              "checks": checks, "setup": setup, "batch": batch, "timeout": timeout, "mergeMethod": merge_method, "paused": ""}
    fixed = ("commonDir", "trunk", "mode", "remote")

    def refuse_clash(current):
        current = {**current, "mode": LEGACY_MODES.get(current.get("mode"), current.get("mode"))} if "mode" in current else current
        clash = [key for key in fixed if key in current and current[key] != wanted[key]]
        if clash:
            raise LandError(f"the contract already sets {', '.join(f'{k}={current[k]!r}' for k in clash)}; "
                            "change the mode with land.py mode; changing trunk or remote needs a new repository contract")

    refuse_clash(store.contract)
    if mode in REMOTE_MODES:
        if not git("remote", "get-url", remote, cwd=repo, check=False).stdout.strip():
            raise LandError(f"mode {mode} needs remote {remote!r}; use --mode local for a repository without one")
        git("fetch", remote, trunk, cwd=repo)
    with store.tx() as db:
        current = {row["key"]: json.loads(row["value"]) for row in db.execute("SELECT key, value FROM contract")}
        refuse_clash(current)
        for key, value in wanted.items():
            if key != "paused" or key not in current:
                db.execute("INSERT OR REPLACE INTO contract VALUES (?, ?)", (key, json.dumps(value)))
        if cap is not None:
            set_cap(db, cap)
    if mode == "local" and git("rev-parse", "--verify", "--quiet", trunk_ref(wanted), cwd=repo, check=False).returncode != 0:
        if not base:
            raise LandError(f"local mode lands on {trunk_ref(wanted)}; pass --base <commit> to create it")
        git("update-ref", trunk_ref(wanted), git("rev-parse", "--verify", f"{base}^{{commit}}", cwd=repo).stdout.strip(), "", cwd=repo)
    return f"{'updated' if current else 'created'} {directory}"


def set_cap(db, cap):
    if cap < 0:
        raise LandError(f"cap {cap} is negative; pass 0 to clear it")
    if cap:
        db.execute("INSERT OR REPLACE INTO contract VALUES ('cap', ?)", (json.dumps(cap),))
    else:
        db.execute("DELETE FROM contract WHERE key = 'cap'")


def change_cap(store, cap):
    with store.tx() as db:
        if cap > 0:
            rows = db.execute("SELECT prefix, count FROM share ORDER BY prefix").fetchall()
            total = sum(row["count"] for row in rows)
            if total > cap:
                listed = ", ".join(f"{row['prefix']} {row['count']}" for row in rows)
                raise LandError(f"shares add up to {total} ({listed}), over the cap of {cap}")
        set_cap(db, cap)
        store.log(db, "queue", 0, f"cap {cap}")
    return f"repository cap is now {cap} changes in flight" if cap else "repository cap cleared"


def change_mode(store, mode, merge_method):
    """Switch remote modes while nothing is in flight. A merge method may change while entries wait, because it only affects the next gh pr merge."""
    mode = LEGACY_MODES.get(mode, mode)
    seen = store.contract["mode"]
    if "local" in (mode, seen) and mode != seen:
        raise LandError("local mode lands on refs/landing/<trunk>, not the remote trunk; switching to or from it needs a new contract")
    allowed = None
    if merge_method or mode == "merge":
        allowed = allowed_merge_methods(store.repo)
        if merge_method:
            pick_merge_method(merge_method, allowed)
    with store.tx() as db:
        # The read above can go stale while gh runs. This one decides the write.
        current = json.loads(db.execute("SELECT value FROM contract WHERE key = 'mode'").fetchone()["value"])
        current = LEGACY_MODES.get(current, current)
        if "local" in (mode, current) and mode != current:
            raise LandError("local mode lands on refs/landing/<trunk>, not the remote trunk; switching to or from it needs a new contract")
        busy = db.execute("SELECT count(*) FROM entry WHERE state IN ('queued', 'landing', 'awaiting-merge')").fetchone()[0]
        if busy and (mode != current or not merge_method):
            raise LandError(busy_queue_message(busy))
        db.execute("INSERT OR REPLACE INTO contract VALUES ('mode', ?)", (json.dumps(mode),))
        method = merge_method
        if not method and mode == "merge" and allowed is not None:
            # Check the method stored now, not the one stored before gh ran.
            method = None if (store.contract.get("mergeMethod") or "merge") in allowed else pick_merge_method(None, allowed)
        if method:
            db.execute("INSERT OR REPLACE INTO contract VALUES ('mergeMethod', ?)", (json.dumps(method),))
        store.log(db, "queue", 0, f"mode {mode}", f"was {current}")
        holders = holders_of(in_flight(db))
    return (f"landing mode is now {mode}" + (f", merging with --{method}" if method else "")
            + (f"; leases held by {holders}" if holders else ""))


def in_flight(db):
    """Leases not yet released: every submitted lease and every active lease that has not expired."""
    return db.execute("SELECT * FROM lease WHERE state = 'submitted' OR (state = 'active' AND expires > ?) ORDER BY id",
                      (stamp(),)).fetchall()


def holders_of(rows):
    return ", ".join(sorted({row["holder"] for row in rows}))


def lease_paths(row):
    return row["paths"].replace("\n", ", ") or "(whole repo)"


def held_on(row):
    return f"L{row['id']} held by {row['holder']} on {lease_paths(row)}"


def standing(db):
    """Reservations that still refuse other holders: waiting, or armed and not expired."""
    return db.execute("SELECT * FROM reservation WHERE state = 'standing' AND (armed = '' OR expires > ?) ORDER BY id",
                      (stamp(),)).fetchall()


def taken_ids(text):
    return [int(part) for part in text.split("\n") if part]


def add_taken(text, lease):
    ids = taken_ids(text)
    if lease not in ids:
        ids.append(lease)
    return "\n".join(str(ident) for ident in ids)


def counts(row, leases):
    """An armed reservation counts as one change in flight while the winner holds no live lease taken from it."""
    live = {lease["id"] for lease in leases}
    return bool(row["armed"]) and not any(ident in live for ident in taken_ids(row["taken"]))


def under(prefix, leases, reservations):
    return sum(lease["holder"].startswith(prefix) for lease in leases) + sum(r["prefix"].startswith(prefix) for r in reservations)


def reserved_for(row):
    hours = "1 hour" if row["ttl"] == 1 else f"{row['ttl']:g} hours"
    until = row["expires"][:16] if row["armed"] else f"{hours} after it arms"
    return f"paths reserved for {row['prefix']} by ruling {row['ruling']} until {until}"


def arm_reservations(store, db, leases, cap):
    """Start the clock of each waiting reservation, oldest first, once its paths are free and there is room for it."""
    shares = db.execute("SELECT * FROM share").fetchall()
    for row in standing(db):
        paths = row["paths"].split("\n")
        if row["armed"] or any(not lease["holder"].startswith(row["prefix"]) and overlaps(paths, lease["paths"].split("\n"))
                               for lease in leases):
            continue
        counting = [r for r in standing(db) if counts(r, leases)]
        if cap and len(leases) + len(counting) >= cap:
            continue
        if any(row["prefix"].startswith(share["prefix"]) and under(share["prefix"], leases, counting) >= share["count"]
               for share in shares):
            continue
        moment = now()
        db.execute("UPDATE reservation SET armed = ?, expires = ? WHERE id = ?",
                   (stamp(moment), stamp(moment + timedelta(hours=row["ttl"])), row["id"]))
        store.log(db, "reservation", row["id"], "armed")


def admission(store, db, holder, wanted, renewing=None):
    """Arm what can arm, then test a lease on these paths for holder.

    Returns the other holders' overlapping leases, a refusal, and the standing reservations the lease takes from.
    Run it inside the transaction that writes the lease, so two claims cannot both pass. A caller that writes a
    lease still commits when refused, so arming is never lost to a refused claim. lease check runs it in
    Store.trial, which rolls back, so a check arms no reservation and adds no log row. renewing is an expired
    lease id. A reservation that already lists it is taken again and left out of the count, so that renewal
    fits a full cap.
    """
    leases, cap = in_flight(db), store.contract.get("cap")
    arm_reservations(store, db, leases, cap)
    clash = [row for row in leases if row["holder"] != holder and overlaps(wanted, row["paths"].split("\n"))]
    if clash:
        return clash, "", []
    reserved = [row for row in standing(db) if overlaps(wanted, row["paths"].split("\n"))]
    blocked = [row for row in reserved if not holder.startswith(row["prefix"])]
    if blocked:
        return [], "; ".join(reserved_for(row) for row in blocked), []
    taken = [row["id"] for row in reserved]
    if renewing is not None:
        taken += [row["id"] for row in standing(db) if row["id"] not in taken and renewing in taken_ids(row["taken"])]
    others = [row for row in standing(db) if counts(row, leases) and row["id"] not in taken]
    count = len(leases) + len(others)
    if cap and count >= cap:
        names = ([holders_of(leases)] if leases else []) + [f"S{row['id']} for {row['prefix']}" for row in others]
        return [], f"repository at its cap: {count} of {cap} changes in flight ({', '.join(names)})", []
    for share in db.execute("SELECT * FROM share ORDER BY prefix"):
        used = under(share["prefix"], leases, others)
        if holder.startswith(share["prefix"]) and used >= share["count"]:
            return [], f"{share['prefix']} is at its share: {used} of {share['count']}", []
    return [], "", taken


def take(store, db, taken, lease, wanted):
    """Release the reserved paths a winner's lease covers. The rest stay reserved."""
    for ident in taken:
        row = db.execute("SELECT * FROM reservation WHERE id = ?", (ident,)).fetchone()
        left = [path for path in row["paths"].split("\n") if not covered(path, wanted)]
        state = "standing" if left else "claimed"
        db.execute("UPDATE reservation SET paths = ?, taken = ?, state = ? WHERE id = ?",
                   ("\n".join(left), add_taken(row["taken"], lease), state, ident))
        store.log(db, "reservation", ident, state, f"L{lease}")


def wanted_paths(paths):
    return sorted({canonical(p) for p in paths.split(",")})


def parse_owner(text):
    match = re.fullmatch(r"(.+/)@(\d+)", text or "")
    if not match:
        raise LandError(f"{text!r} is not an owner such as docs/@2")
    return match.group(1), int(match.group(2))


def check_owner(db, holder, owner):
    """Refuse a write by a replaced coordinator. Run it inside the write's transaction."""
    if owner is not None:
        prefix, generation = parse_owner(owner)
        if not holder.startswith(prefix):
            raise LandError(f"owner {owner} does not cover holder {holder}")
    for row in db.execute("SELECT * FROM owner ORDER BY prefix"):
        if not holder.startswith(row["prefix"]):
            continue
        if owner is None or prefix != row["prefix"]:
            raise LandError(f"{holder} is under {row['prefix']} at generation {row['generation']}; "
                            f"pass --owner {row['prefix']}@{row['generation']}")
        if generation < row["generation"]:
            raise LandError(f"owner {owner} is stale; {prefix} is at generation {row['generation']}")


def check_ruling_owner(db, owner):
    """Refuse a ruling write by a replaced admin. Run it first inside the write's transaction."""
    prefix, generation = parse_owner(owner)
    row = db.execute("SELECT generation FROM owner WHERE prefix = ?", (prefix,)).fetchone()
    if row and generation < row["generation"]:
        raise LandError(f"owner {owner} is stale; {prefix} is at generation {row['generation']}")


def holder_prefix(prefix):
    if not prefix.endswith("/"):
        raise LandError(f"{prefix!r} is not a holder prefix such as docs/")


def raise_floor(store, prefix, generation):
    holder_prefix(prefix)
    with store.tx() as db:
        row = db.execute("SELECT generation FROM owner WHERE prefix = ?", (prefix,)).fetchone()
        if row and row["generation"] > generation:
            raise LandError(f"{prefix} is at generation {row['generation']}; a floor never lowers")
        if not row or row["generation"] < generation:
            db.execute("INSERT OR REPLACE INTO owner VALUES (?, ?)", (prefix, generation))
            store.log(db, "owner", generation, "raised", prefix)
    return f"{prefix} at generation {generation}"


def lease_claim(store, holder, paths, ttl_hours, owner=None):
    wanted = wanted_paths(paths)
    with store.tx() as db:
        check_owner(db, holder, owner)
        clash, refusal, taken = admission(store, db, holder, wanted)
        if not clash and not refusal:
            cursor = db.execute("INSERT INTO lease (at, holder, paths, state, expires) VALUES (?, ?, ?, 'active', ?)",
                                (stamp(), holder, "\n".join(wanted), stamp(now() + timedelta(hours=ttl_hours))))
            store.log(db, "lease", cursor.lastrowid, "active", holder)
            take(store, db, taken, cursor.lastrowid, wanted)
    if clash:
        raise LandError("paths overlap " + "; ".join(held_on(row) for row in clash))
    if refusal:
        raise LandError(refusal)
    return f"L{cursor.lastrowid}"


def lease_check(store, holder, paths):
    with store.trial() as db:
        clash, refusal, _taken = admission(store, db, holder, wanted_paths(paths))
    if clash or refusal:
        return "\n".join(held_on(row) for row in clash) or refusal, 1
    return "free", 0


def lease_renew(store, number, ttl_hours, if_live, owner=None):
    """Extend a live lease. An expired lease is admitted again, as a new claim on its paths would be."""
    clash, refusal = [], ""
    with store.tx() as db:
        row = db.execute("SELECT * FROM lease WHERE id = ?", (number,)).fetchone()
        if not row:
            raise LandError(f"no L{number}")
        check_owner(db, row["holder"], owner)
        if row["state"] == "submitted":
            raise LandError(f"L{number} is submitted; the queue holds it")
        if row["state"] == "released":
            raise LandError(f"L{number} is released")
        expired = row["expires"] <= stamp()
        if expired and if_live:
            raise LandError(f"L{number} expired at {row['expires'][:16]}")
        taken = []
        if expired:
            clash, refusal, taken = admission(store, db, row["holder"], row["paths"].split("\n"), renewing=number)
        if not clash and not refusal:
            db.execute("UPDATE lease SET expires = ? WHERE id = ?", (stamp(now() + timedelta(hours=ttl_hours)), number))
            store.log(db, "lease", number, "renewed", "after it expired" if expired else "")
            take(store, db, taken, number, row["paths"].split("\n"))
    if clash:
        covers = " and ".join(f"L{c['id']} held by {c['holder']} now covers {lease_paths(c)}" for c in clash)
        raise LandError(f"L{number} expired and {covers}; claim again after {'it is' if len(clash) == 1 else 'they are'} released")
    if refusal:
        raise LandError(refusal)
    return f"L{number} renewed"


def lease_reserve(store, prefix, paths, ruling, ttl_hours, owner):
    holder_prefix(prefix)
    wanted = wanted_paths(paths)
    # take() never drops an empty path for a narrower lease, so reserving one blocks every other holder until expiry.
    if "" in wanted:
        raise LandError("a reservation names the contested paths; it cannot hold the whole repository")
    with store.tx() as db:
        check_ruling_owner(db, owner)
        row = db.execute("SELECT * FROM reservation WHERE ruling = ?", (ruling,)).fetchone()
        if row:
            state = reservation_state(row)
            if state in ("expired", "lifted"):
                raise LandError(f"S{row['id']} for ruling {ruling} {'expired' if state == 'expired' else 'was lifted'}")
            if state == "claimed":
                return f"S{row['id']} was claimed in full"
            return f"S{row['id']}"
        clash = [r for r in standing(db) if overlaps(wanted, r["paths"].split("\n"))]
        if clash:
            raise LandError("; ".join(f"paths overlap S{r['id']} reserved for {r['prefix']} by ruling {r['ruling']} on {lease_paths(r)}"
                                      for r in clash))
        cursor = db.execute("INSERT INTO reservation (at, prefix, paths, ruling, ttl, state) VALUES (?, ?, ?, ?, ?, 'standing')",
                            (stamp(), prefix, "\n".join(wanted), ruling, ttl_hours))
        store.log(db, "reservation", cursor.lastrowid, "waiting", f"{prefix} by {ruling}")
        arm_reservations(store, db, in_flight(db), store.contract.get("cap"))
    return f"S{cursor.lastrowid}"


def reservation_state(row):
    if row["state"] != "standing":
        return row["state"]
    if not row["armed"]:
        return "waiting"
    return "armed" if row["expires"] > stamp() else "expired"


def lease_unreserve(store, number, owner):
    """Every outcome but a missing reservation exits 0, so a replacing ruling converges."""
    with store.tx() as db:
        check_ruling_owner(db, owner)
        row = db.execute("SELECT * FROM reservation WHERE id = ?", (number,)).fetchone()
        if not row:
            raise LandError(f"no S{number}")
        state = reservation_state(row)
        if state == "claimed":
            return f"S{number} was claimed in full"
        if state == "expired":
            return f"S{number} expired at {row['expires'][:16]}"
        if state != "lifted":
            db.execute("UPDATE reservation SET state = 'lifted' WHERE id = ?", (number,))
            store.log(db, "reservation", number, "lifted")
    return f"S{number} lifted"


def lease_list(store):
    lines = [f"L{r['id']} {r['state']} {r['holder']} until {r['expires'][:16]}: {lease_paths(r)}" for r in in_flight(store.db)]
    for row in standing(store.db):
        until = f" until {row['expires'][:16]}" if row["armed"] else ""
        lines.append(f"S{row['id']} {reservation_state(row)} {row['prefix']} by {row['ruling']}{until}: {lease_paths(row)}")
    return "\n".join(lines) or "no leases held"


def change_share(store, prefix, count, clear, owner):
    holder_prefix(prefix)
    if clear and count != 0:
        raise LandError("--clear takes 0")
    if count < 0:
        raise LandError(f"share {count} is negative")
    with store.tx() as db:
        check_ruling_owner(db, owner)
        row = db.execute("SELECT count FROM share WHERE prefix = ?", (prefix,)).fetchone()
        if clear:
            if row:
                db.execute("DELETE FROM share WHERE prefix = ?", (prefix,))
                store.log(db, "share", 0, "cleared", prefix)
            return f"{prefix} share cleared"
        if row and row["count"] == count:
            return f"{prefix} share is {count}"
        cap = store.contract.get("cap")
        total = count + db.execute("SELECT coalesce(sum(count), 0) FROM share WHERE prefix != ?", (prefix,)).fetchone()[0]
        if cap and total > cap:
            raise LandError(f"shares would add up to {total}, over the cap of {cap}")
        db.execute("INSERT OR REPLACE INTO share VALUES (?, ?)", (prefix, count))
        store.log(db, "share", count, "set", prefix)
    return f"{prefix} share is {count}"


def lease_release(store, number, owner=None):
    with store.tx() as db:
        row = db.execute("SELECT * FROM lease WHERE id = ?", (number,)).fetchone()
        if row:
            check_owner(db, row["holder"], owner)
        if not row or row["state"] != "active":
            raise LandError(f"L{number} is not active; a submitted lease is released when its entry lands or bounces")
        release_lease(store, db, number)
    return f"L{number} released"


def release_lease(store, db, number, note=""):
    """Release a lease and arm reservations that were waiting only on it."""
    db.execute("UPDATE lease SET state = 'released' WHERE id = ?", (number,))
    store.log(db, "lease", number, "released", note)
    arm_reservations(store, db, in_flight(db), store.contract.get("cap"))


def lease_id(text):
    if not re.fullmatch(r"L?\d+", text or ""):
        raise LandError(f"{text!r} is not a lease id such as L3")
    return int(text.lstrip("L"))


def reservation_id(text):
    if not re.fullmatch(r"S?\d+", text or ""):
        raise LandError(f"{text!r} is not a reservation id such as S3")
    return int(text.lstrip("S"))


def entry_label(ident):
    return f"E{ident}"


def entry_id(text):
    """E<n> names an entry. A bare number is the id."""
    if not re.fullmatch(r"E?\d+", text or ""):
        raise LandError(f"{text!r} is not an entry id such as E3")
    return int(text.lstrip("E"))


def submit(store, holder, branch, sha, lease, reviewer, title="", body="", owner=None):
    contract, repo = store.contract, store.repo
    lease_number = lease_id(lease)
    sha = git("rev-parse", "--verify", f"{sha}^{{commit}}", cwd=repo).stdout.strip()
    if contract["mode"] != "local":
        git("fetch", contract["remote"], contract["trunk"], cwd=repo)
    base = git("merge-base", trunk_ref(contract), sha, cwd=repo).stdout.strip()
    if git("rev-list", "--merges", f"{base}..{sha}", cwd=repo).stdout.strip():
        raise LandError(f"{branch} has merge commits; make its history linear on {contract['trunk']} first")
    files = [canonical(f, "changed") for f in changed_paths(repo, base, sha)]
    if not files:
        raise LandError(f"{sha[:12]} changes nothing relative to {contract['trunk']}")
    print_ = fingerprint(repo, base, sha)
    git("update-ref", pin_ref(sha), sha, cwd=repo)
    with store.tx() as db:
        check_owner(db, holder, owner)
        existing = db.execute("SELECT id, state FROM entry WHERE sha = ? AND holder = ?", (sha, holder)).fetchone()
        if existing and existing["state"] != "bounced":
            return f"{entry_label(existing['id'])} already {existing['state']}"
        row = db.execute("SELECT * FROM lease WHERE id = ?", (lease_number,)).fetchone()
        if not row or row["holder"] != holder or row["state"] != "active" or row["expires"] <= stamp():
            raise LandError(f"L{lease_number} is not an active lease held by {holder}; claim one before submitting")
        outside = [f for f in files if not covered(f, row["paths"].split("\n"))]
        if outside:
            raise LandError(f"changes paths outside L{lease_number}: {', '.join(outside)}; widen the lease or split the change")
        if existing:
            db.execute("DELETE FROM entry WHERE id = ?", (existing["id"],))
        cursor = db.execute("INSERT INTO entry (at, holder, branch, sha, base, fingerprint, lease, reviewer, state, title, body) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?)",
                            (stamp(), holder, branch, sha, base, print_, lease_number, reviewer, title, body))
        db.execute("UPDATE lease SET state = 'submitted' WHERE id = ?", (lease_number,))
        store.log(db, "entry", cursor.lastrowid, "queued", f"{holder}: {branch}")
    return entry_label(cursor.lastrowid)


def cherry_pick_stopped_for_conflict(result):
    """True when this cherry-pick stopped on a conflict.

    rerere.autoupdate can stage a resolution that matches HEAD. The index is then
    clean and the exit status is nonzero, the same as a commit that became empty.
    A conflict prints CONFLICT or "could not apply". An empty commit does not.
    """
    detail = result.stderr + result.stdout
    return "CONFLICT" in detail or "could not apply" in detail


class Integration:
    """A detached worktree only the queue uses, restored to a clean base before every attempt."""

    def __init__(self, store):
        self.store = store
        self.path = store.dir / "integration"
        if not (self.path / ".git").exists():
            git("worktree", "add", "--detach", str(self.path), trunk_ref(store.contract), cwd=store.repo)

    def git(self, *args, check=True):
        return git(*args, cwd=self.path, check=check)

    def reset(self, commit):
        for operation in ("cherry-pick", "rebase", "merge"):
            self.git(operation, "--abort", check=False)
        self.git("checkout", "--force", "--detach", commit)
        self.git("reset", "--hard", commit)
        self.git("clean", "-ffdx")

    def head(self):
        return self.git("rev-parse", "HEAD").stdout.strip()

    def apply(self, entry):
        """Replay the pinned commits onto HEAD. Returns None, or why the entry cannot land."""
        before = self.head()
        spec = f"{entry['base']}..{pin_ref(entry['sha'])}"
        identity = committer(self.path)
        result = self.git(*identity, "-c", "rerere.enabled=false", "cherry-pick", spec, check=False)
        # git 2.43 has no cherry-pick --empty=drop. Git added it in 2.45. Drop a commit that
        # became empty, and stop on a commit that started empty. That matches --empty=drop.
        if result.returncode != 0:
            counted = self.git("rev-list", "--count", spec, check=False)
            remaining = int(counted.stdout.strip() or "0") if counted.returncode == 0 else 0
            while result.returncode != 0 and remaining > 0 and not cherry_pick_stopped_for_conflict(result):
                picked = self.git("rev-parse", "-q", "--verify", "CHERRY_PICK_HEAD", check=False)
                if picked.returncode != 0:
                    break
                sha = picked.stdout.strip()
                parent_tree = self.git("rev-parse", "-q", "--verify", f"{sha}^^{{tree}}", check=False)
                own_tree = self.git("rev-parse", "-q", "--verify", f"{sha}^{{tree}}", check=False)
                started_empty = parent_tree.returncode == 0 and parent_tree.stdout.strip() == own_tree.stdout.strip()
                dirty = (self.git("diff", "--quiet", check=False).returncode != 0
                         or self.git("diff", "--cached", "--quiet", check=False).returncode != 0)
                unmerged = bool(self.git("ls-files", "-u", check=False).stdout.strip())
                if started_empty or dirty or unmerged:
                    break
                result = self.git(*identity, "-c", "rerere.enabled=false", "cherry-pick", "--skip", check=False)
                remaining -= 1
        if result.returncode != 0:
            self.git("cherry-pick", "--abort", check=False)
            self.git("reset", "--hard", before)
            if cherry_pick_stopped_for_conflict(result):
                return "conflict with trunk"
            detail = (result.stderr + result.stdout).strip()
            raise Infrastructure("cherry-pick failed: " + (detail.splitlines() or ["no output"])[-1])
        if self.head() == before:
            return "already-in-trunk"
        if fingerprint(self.path, before, self.head()) != entry["fingerprint"]:
            self.git("reset", "--hard", before)
            return "the rebased change differs from the reviewed one; review it again"
        return None

    def check(self):
        """Run setup and checks on the candidate. Returns None, or the failure. Raises when the run left the tree dirty."""
        contract = self.store.contract
        expected = self.head()
        with slot("landing"):
            for command in ([contract["setup"]] if contract.get("setup") else []) + contract["checks"]:
                code, output = supervised(command, self.path, contract.get("timeout") or 1800)
                if code != 0:
                    tail = " / ".join(output.strip().splitlines()[-3:])
                    reason = "timed out" if code is None else f"exited {code}"
                    return f"`{command}` {reason}: {tail}"
        if self.head() != expected or self.git("status", "--porcelain", "--untracked-files=no").stdout.strip():
            raise LandError("a check changed tracked files in the integration worktree; fix the check, then run land again")
        return None


def remote_trunk(store):
    contract = store.contract
    line = git("ls-remote", contract["remote"], f"refs/heads/{contract['trunk']}", cwd=store.repo).stdout.split()
    return line[0] if line else ""


def publish(store, base, candidate):
    """Move trunk from exactly base to candidate. Returns None, or why not."""
    contract, repo = store.contract, store.repo
    if git("merge-base", "--is-ancestor", base, candidate, cwd=repo, check=False).returncode != 0:
        raise LandError(f"candidate {candidate[:12]} does not descend from {base[:12]}")
    if contract["mode"] == "local":
        result = git("update-ref", trunk_ref(contract), candidate, base, cwd=repo, check=False)
        return None if result.returncode == 0 else "trunk moved during landing"
    result = git_push(f"--force-with-lease=refs/heads/{contract['trunk']}:{base}", contract["remote"],
                      f"{candidate}:refs/heads/{contract['trunk']}", cwd=repo, check=False)
    if result.returncode != 0:
        if remote_trunk(store) != base:
            return "trunk moved during landing"
        raise Infrastructure("push rejected: " + git_reason(result.stderr))
    git("fetch", contract["remote"], contract["trunk"], cwd=repo)
    return None


def pause(store, reason):
    with store.tx() as db:
        db.execute("INSERT OR REPLACE INTO contract VALUES ('paused', ?)", (json.dumps(reason),))
        store.log(db, "queue", 0, "paused", reason)


def forget_absent(db, ident):
    """Drop this entry's drain marker. A settled entry must not stay in the map."""
    row = db.execute("SELECT value FROM contract WHERE key = 'absentDrain'").fetchone()
    if not row:
        return
    raw = json.loads(row["value"])
    if str(ident) not in raw:
        return
    del raw[str(ident)]
    db.execute("INSERT OR REPLACE INTO contract VALUES ('absentDrain', ?)", (json.dumps(raw),))


def settle_landed(store, db, ident, landed, note=""):
    forget_absent(db, ident)
    lease = db.execute("SELECT lease FROM entry WHERE id = ?", (ident,)).fetchone()["lease"]
    store.set_entry(db, ident, "landed", landed=landed, note=note)
    release_lease(store, db, lease, f"{entry_label(ident)} landed")


def settle_bounced(store, db, ident, reason):
    """A bounced entry gives its lease back to the holder for the fix, with a fresh expiry."""
    forget_absent(db, ident)
    lease = db.execute("SELECT lease FROM entry WHERE id = ?", (ident,)).fetchone()["lease"]
    store.set_entry(db, ident, "bounced", note=reason, candidate="")
    db.execute("UPDATE lease SET state = 'active', expires = ? WHERE id = ?", (stamp(now() + timedelta(hours=6)), lease))
    store.log(db, "lease", lease, "active", f"{entry_label(ident)} bounced; the lease is back for the fix")


def reconcile(store):
    """Settle what a crashed run left behind, by asking git what actually happened."""
    contract, repo = store.contract, store.repo
    if contract["mode"] != "local":
        git("fetch", contract["remote"], contract["trunk"], cwd=repo)
    for attempt in store.db.execute("SELECT * FROM attempt WHERE state = 'publishing'").fetchall():
        published = git("merge-base", "--is-ancestor", attempt["candidate"], trunk_ref(contract), cwd=repo, check=False).returncode == 0
        with store.tx() as db:
            for ident in json.loads(attempt["entries"]):
                if published:
                    settle_landed(store, db, ident, attempt["candidate"], "recovered after an interrupted run")
                else:
                    store.set_entry(db, ident, "queued", candidate="", note="requeued after an interrupted run")
            db.execute("UPDATE attempt SET state = ? WHERE id = ?", ("published" if published else "abandoned", attempt["id"]))
    with store.tx() as db:
        for entry in db.execute("SELECT id FROM entry WHERE state = 'landing'").fetchall():
            store.set_entry(db, entry["id"], "queued", candidate="", note="requeued after an interrupted run")


def rewound(store, base):
    """Pause when trunk no longer contains the last landed commit. Returns True when paused."""
    tip = store.contract.get("tip") or ""
    if tip and git("merge-base", "--is-ancestor", tip, base, cwd=store.repo, check=False).returncode != 0:
        pause(store, f"trunk no longer contains the last landed commit {tip[:12]} (now {base[:12]}); "
                     "check what happened to trunk, then run land.py resume")
        return True
    return False


def attempt(store, integration, entries):
    """Rebase entries onto trunk, check once, publish. Returns (landed ids, bounced ids, requeued ids, base)."""
    contract = store.contract
    if contract["mode"] != "local":
        git("fetch", contract["remote"], contract["trunk"], cwd=store.repo)
    base = git("rev-parse", trunk_ref(contract), cwd=store.repo).stdout.strip()
    if rewound(store, base):
        return [], [], [], base
    integration.reset(base)
    applied, bounced, landed = [], [], []
    for entry in entries:
        reason = integration.apply(entry)
        candidate = "" if reason else integration.head()
        with store.tx() as db:
            if reason == "already-in-trunk":
                settle_landed(store, db, entry["id"], base, "already in trunk")
                landed.append(entry["id"])
            elif reason:
                settle_bounced(store, db, entry["id"], reason)
                bounced.append(entry["id"])
            else:
                store.set_entry(db, entry["id"], "landing", candidate=candidate)
                applied.append(entry)
    if not applied:
        return landed, bounced, [], base
    failure = integration.check()
    if failure:
        with store.tx() as db:
            if len(applied) > 1:
                for entry in applied:
                    store.set_entry(db, entry["id"], "queued", candidate="", note="batch failed checks; landing one at a time")
                return landed, bounced, [entry["id"] for entry in applied], base
            settle_bounced(store, db, applied[0]["id"], f"checks failed: {failure}")
            return landed, bounced + [applied[0]["id"]], [], base
    candidate = integration.head()
    with store.tx() as db:
        cursor = db.execute("INSERT INTO attempt (at, base, candidate, entries, state) VALUES (?, ?, ?, ?, 'publishing')",
                            (stamp(), base, candidate, json.dumps([entry["id"] for entry in applied])))
    problem = publish(store, base, candidate)
    with store.tx() as db:
        db.execute("UPDATE attempt SET state = ? WHERE id = ?", ("abandoned" if problem else "published", cursor.lastrowid))
        for entry in applied:
            if problem:
                store.set_entry(db, entry["id"], "queued", candidate="", note=problem)
            else:
                settle_landed(store, db, entry["id"], candidate)
        if not problem:
            db.execute("INSERT OR REPLACE INTO contract VALUES ('tip', ?)", (json.dumps(candidate),))
    if problem:
        return landed, bounced, [entry["id"] for entry in applied], base
    return landed + [entry["id"] for entry in applied], bounced, [], candidate


def gh(*args, cwd):
    return subprocess.run([os.environ.get("LAND_GH", "gh"), *args], cwd=cwd, capture_output=True, text=True)


def land_human(store, integration, entry):
    """Human mode: rebase onto trunk, check, push to a queue-owned branch, open its PR. Returns True when opened."""
    contract = store.contract
    git("fetch", contract["remote"], contract["trunk"], cwd=store.repo)
    base = git("rev-parse", trunk_ref(contract), cwd=store.repo).stdout.strip()
    integration.reset(base)
    reason = integration.apply(entry)
    if not reason:
        reason = integration.check()
        reason = f"checks failed: {reason}" if reason else None
    if reason == "already-in-trunk":
        with store.tx() as db:
            settle_landed(store, db, entry["id"], base, "already in trunk")
        return False
    if reason:
        with store.tx() as db:
            settle_bounced(store, db, entry["id"], reason)
        return False
    head = integration.head()
    push = git_push("--force", contract["remote"], f"{head}:refs/heads/{human_branch(entry)}", cwd=store.repo, check=False)
    if push.returncode != 0:
        raise Infrastructure("push failed: " + git_reason(push.stderr))
    with store.tx() as db:
        store.set_entry(db, entry["id"], "awaiting-merge", candidate=head, pr="", note="")
    return ensure_pr(store, {**dict(entry), "candidate": head})


def human_branch(entry):
    return f"landing/e{entry['id']}"


def publish_absent_branch(store, entry, branch):
    """Push the checked candidate when the entry's branch is not on the remote.

    An entry queued by an older queue stores a candidate whose branch was
    never pushed as landing/e<n>, so gh pr create refuses the name. The push
    sends the commit the queue already checked. A branch that is already on
    the remote is left where it is."""
    candidate = (entry["candidate"] or "").strip()
    if not candidate:
        return
    remote = store.contract["remote"]
    listed = git("ls-remote", "--heads", remote, f"refs/heads/{branch}", cwd=store.repo, check=False)
    if listed.returncode != 0 or listed.stdout.strip():
        return
    push = git_push("--force", remote, f"{candidate}:refs/heads/{branch}", cwd=store.repo, check=False)
    if push.returncode != 0:
        raise Infrastructure("push failed: " + git_reason(push.stderr))


def pr_adoptable_url(store, entry, branch):
    """URL of a pull request on this branch that belongs to this entry.

    An open pull request counts. A closed or merged one counts only when its
    head is this entry's stored candidate. Any other pull request on the name
    is a reused id. With no stored candidate, only an open pull request counts.
    """
    candidate = (entry["candidate"] or "").strip()
    if candidate:
        fields = "url,state,headRefOid"
        query = f'select(.state == "OPEN" or .headRefOid == "{candidate}") | .url'
    else:
        fields = "url,state"
        query = 'select(.state == "OPEN") | .url'
    found = gh("pr", "view", branch, "--json", fields, "-q", query, cwd=store.repo)
    if found.returncode != 0:
        return ""
    return found.stdout.strip()


def ensure_pr(store, entry):
    """Store this entry's PR. Open one on landing/e<n> when that name has none this entry can use.

    A pull request on landing/e<n> is adopted only by pr_adoptable_url. A
    reused id publishes landing/e<n> and opens the pull request there. A crash
    after gh pr create and before the URL is stored is safe to rerun. Returns
    "adopted" when an existing pull request was stored, and "created" when
    this run opened one."""
    contract = store.contract
    branch = human_branch(entry)
    url = pr_adoptable_url(store, entry, branch)
    adopted = bool(url)
    if not url:
        publish_absent_branch(store, entry, branch)
        title = entry["title"] or git("log", "-1", "--format=%s", entry["sha"], cwd=store.repo).stdout.strip()
        body = entry["body"] or git("log", "-1", "--format=%b", entry["sha"], cwd=store.repo).stdout.rstrip()
        created = gh("pr", "create", "--base", contract["trunk"], "--head", branch, "--title", title, "--body", body, cwd=store.repo)
        if created.returncode != 0:
            raise Infrastructure("gh pr create failed: " + created.stderr.strip())
        url = created.stdout.strip().splitlines()[-1]
        adopted = False
    with store.tx() as db:
        store.set_entry(db, entry["id"], "awaiting-merge", pr=url, note="")
    if contract["mode"] == "merge":
        request_merge(store, entry["id"], url)
    return "adopted" if adopted else "created"


MERGE_REQUESTED = "merge requested by the queue"


WAITING_FOR_CHECKS = "waiting for required checks before merging"
BLOCKER_QUERY = (
    '[.reviewDecision // "", '
    '([(.statusCheckRollup // [])[] | select((.status // "COMPLETED") != "COMPLETED" or (.state // "") == "PENDING")] | length), '
    '([(.statusCheckRollup // [])[] | select((.conclusion // "") as $c | (.state // "") as $s '
    '| ($c == "FAILURE" or $c == "CANCELLED" or $c == "TIMED_OUT" or $s == "FAILURE" or $s == "ERROR")) '
    '| (.name // .context)] | join(",")), '
    '((.statusCheckRollup // []) | length), '
    '(.autoMergeRequest != null)] | @tsv'
)


def classify_rollup(review, pending, failed, posted):
    """The gate for one check read. Absent means GitHub has posted nothing yet."""
    if review in ("REVIEW_REQUIRED", "CHANGES_REQUESTED"):
        return "review", review
    if failed:
        return "failed", failed
    if pending > 0:
        return "pending", ""
    if posted == 0:
        return "absent", ""
    return "", ""


def unposted_merge_refusal(stderr):
    """The plain merge was refused by base branch policy while no check is posted."""
    return "the base branch policy prohibits the merge" in (stderr or "")


def advance_drain(store):
    """Count this land run. The same run polls twice, so an empty rollup waits for a later run."""
    nxt = int(store.contract.get("drain") or 0) + 1
    with store.tx() as db:
        db.execute("INSERT OR REPLACE INTO contract VALUES ('drain', ?)", (json.dumps(nxt),))
    return nxt


def absent_seen(store, ident):
    raw = store.contract.get("absentDrain") or {}
    value = raw.get(str(ident))
    return None if value is None else int(value)


def remember_absent(store, ident, drain):
    with store.tx() as db:
        row = db.execute("SELECT value FROM contract WHERE key = 'absentDrain'").fetchone()
        raw = json.loads(row["value"]) if row else {}
        raw.setdefault(str(ident), drain)
        db.execute("INSERT OR REPLACE INTO contract VALUES ('absentDrain', ?)", (json.dumps(raw),))
        store.set_entry(db, ident, "awaiting-merge", note=WAITING_FOR_CHECKS)


def merge_blocker(store, url):
    """Why this PR must not merge yet, and whether auto-merge is requested.

    One gh pr view supplies the review, the pending count, the failed names, how many
    checks are posted, and whether autoMergeRequest is set. Returns the classify_rollup
    pair plus True when autoMergeRequest is not null. A failed command or an unparseable
    rollup raises Infrastructure, and the caller must not merge."""
    view = gh("pr", "view", url, "--json", "reviewDecision,statusCheckRollup,autoMergeRequest", "-q", BLOCKER_QUERY, cwd=store.repo)
    if view.returncode != 0:
        raise Infrastructure(f"could not read checks for {url}: {view.stderr.strip() or 'gh pr view failed'}")
    fields = view.stdout.rstrip("\n").split("\t")
    if len(fields) != 5 or not fields[1].isdigit() or not fields[3].isdigit() or fields[4] not in ("true", "false"):
        raise Infrastructure(f"could not read checks for {url}: unparseable check rollup")
    blocker, detail = classify_rollup(fields[0], int(fields[1]), fields[2], int(fields[3]))
    return blocker, detail, fields[4] == "true"


def disarm_auto_merge(store, url, armed):
    """Turn auto-merge off when the check read showed an autoMergeRequest.

    An empty return means it is off or was never requested. A string is a failure of
    gh pr merge --disable-auto."""
    if not armed:
        return ""
    result = gh("pr", "merge", url, "--disable-auto", cwd=store.repo)
    if result.returncode == 0:
        return ""
    return (result.stderr or result.stdout or "gh pr merge --disable-auto failed").strip()


def bounce_open_pr(store, ident, url, reason, armed):
    """Bounce an open merge-mode PR. Disable auto-merge when it is on, and leave the PR open.

    A PR whose auto-merge stays on can still merge without the queue, so the queue pauses and keeps tracking it."""
    problem = disarm_auto_merge(store, url, armed)
    if problem:
        raise AutoMergeStillEnabled(
            f"{reason}. Auto-merge is still enabled: {problem}. "
            f"Turn auto-merge off on {url}, then run land.py resume and land.py land")
    with store.tx() as db:
        settle_bounced(store, db, ident, reason)


def pause_for_review(store, url, detail, disarm, armed=False):
    problem = disarm_auto_merge(store, url, armed) if disarm else ""
    requirement = "has changes requested" if detail == "CHANGES_REQUESTED" else "needs an approving review"
    if problem:
        raise Infrastructure(f"{url} {requirement}. Auto-merge is still enabled: {problem}")
    raise Infrastructure(f"{url} {requirement}")


def request_merge(store, ident, url):
    """Merge only after a successful check read shows nothing pending, failed, or awaiting review.

    The read runs before any gh pr merge, including --auto. A pending posted check waits.
    A failed posted check bounces. With no posted check, the land run that first sees it
    waits. A later land merges when checks are still absent. While checks are still absent,
    the queue waits and does not pause only when the plain merge itself is refused because
    the base branch policy prohibits the merge. Any other plain-merge failure pauses and
    names that failure, whatever the --auto attempt said. An approving review, or changes
    requested, pauses the queue and does not call gh pr merge."""
    blocker, detail, armed = merge_blocker(store, url)
    if blocker == "review":
        pause_for_review(store, url, detail, disarm=False)
    drain = int(store.contract.get("drain") or 0)
    seen = absent_seen(store, ident)
    repeat_absent = blocker == "absent" and seen is not None and seen < drain
    if blocker == "pending" or (blocker == "absent" and not repeat_absent):
        if blocker == "absent":
            remember_absent(store, ident, drain)
        else:
            with store.tx() as db:
                store.set_entry(db, ident, "awaiting-merge", note=WAITING_FOR_CHECKS)
        return False
    if blocker == "failed":
        bounce_open_pr(store, ident, url, f"required checks failed on {url}: {detail}", armed)
        return False
    method = f"--{store.contract.get('mergeMethod') or 'merge'}"
    queued = gh("pr", "merge", url, "--auto", method, cwd=store.repo)
    if queued.returncode == 0:
        with store.tx() as db:
            store.set_entry(db, ident, "awaiting-merge", note=MERGE_REQUESTED)
        return True
    now_ = gh("pr", "merge", url, method, cwd=store.repo)
    if now_.returncode != 0:
        plain = (now_.stderr or "").strip()
        if blocker == "absent" and unposted_merge_refusal(plain):
            with store.tx() as db:
                store.set_entry(db, ident, "awaiting-merge", note=WAITING_FOR_CHECKS)
            return False
        raise Infrastructure(f"GitHub refused to merge {url}: {plain or 'gh pr merge failed'}")
    with store.tx() as db:
        store.set_entry(db, ident, "awaiting-merge", note=MERGE_REQUESTED)
    return True


_CLIENT_ABSENT_REF = re.compile(r"^error: unable to delete '[^']*': remote ref does not exist$", re.M)
_GITHUB_OWNER_REPO = re.compile(
    r"^(?:https://github\.com/|ssh://git@github\.com/|git://github\.com/|git@github\.com:)"
    r"([^/]+)/([^/]+?)(?:\.git)?/?$"
)


def http_status(text):
    """The status code from an HTTP status line, or None when the text has none."""
    for line in (text or "").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].startswith("HTTP/") and parts[1].isdigit():
            return int(parts[1])
    return None


def forge_branch_status(repo, branch):
    """HTTP status for branch on the forge this checkout already uses for gh pr.

    gh fills {owner} and {repo} from the checkout. 404 means the branch is gone.
    200 means it exists. None means the read did not return a status line."""
    result = gh("api", "--include", "repos/{owner}/{repo}/branches/" + branch, cwd=repo)
    return http_status(result.stdout)


def github_owner_repo(url):
    """owner/repo from a GitHub remote URL, or None when the URL names something else."""
    match = _GITHUB_OWNER_REPO.match((url or "").strip())
    if not match:
        return None
    owner, repo = match.group(1), match.group(2)
    if not owner or not repo or owner in (".", "..") or repo in (".", ".."):
        return None
    return f"{owner}/{repo}"


def push_urls(repo, remote):
    """Every push URL of remote, or None when git cannot list them."""
    listed = git("remote", "get-url", "--push", "--all", remote, cwd=repo, check=False)
    if listed.returncode != 0:
        return None
    return [line.strip() for line in listed.stdout.splitlines() if line.strip()]


def forge_name_with_owner(repo):
    """owner/repo that gh resolves for this checkout, or None when that read fails."""
    viewed = gh("repo", "view", "--json", "nameWithOwner", cwd=repo)
    if viewed.returncode != 0 or not (viewed.stdout or "").strip():
        return None
    try:
        payload = json.loads(viewed.stdout)
    except json.JSONDecodeError:
        return None
    name = payload.get("nameWithOwner") if isinstance(payload, dict) else None
    if not isinstance(name, str) or name.count("/") != 1:
        return None
    owner, repo_name = name.split("/", 1)
    if not owner or not repo_name:
        return None
    return name


def forge_is_only_push_target(store):
    """True when the failed delete went only to the repository gh will be asked about."""
    urls = push_urls(store.repo, store.contract["remote"])
    if urls is None or len(urls) != 1:
        return False
    pushed = github_owner_repo(urls[0])
    if pushed is None:
        return False
    resolved = forge_name_with_owner(store.repo)
    if resolved is None:
        return False
    return pushed.lower() == resolved.lower()


def remote_branch_is_gone(store, entry, branch, stderr):
    """Whether a failed delete left the queue branch absent.

    Merge and human mode ask the forge when the contract remote has exactly
    one push URL and that URL names the same owner/repo gh resolves. The
    forge's answer is final. Only HTTP 404 counts as gone, and any other
    status or no status line leaves the entry.
    With no forge to ask, the queue cannot tell a branch hidden from git
    from a missing one. It then accepts git's absent line only when the
    entry's PR was opened from another branch, which an older queue did.
    That settles an entry whose hidden landing/e<n> still exists. The
    alternative is an entry that can never land.
    Push and local mode accept only git's absent line, and any other
    failure waits for the next run."""
    if store.contract["mode"] in ("merge", "human"):
        if forge_is_only_push_target(store):
            return forge_branch_status(store.repo, branch) == 404
        return opened_on_another_branch(store, entry, branch, stderr)
    return _CLIENT_ABSENT_REF.search(stderr or "") is not None


def forget_local_branch(store, branch):
    """Drop the local branch and its remote-tracking ref. A branch git cannot delete is named in the warning."""
    remote = store.contract["remote"]
    git("update-ref", "-d", f"refs/remotes/{remote}/{branch}", cwd=store.repo, check=False)
    if git("show-ref", "--verify", "--quiet", f"refs/heads/{branch}", cwd=store.repo, check=False).returncode != 0:
        return ""
    local = git("branch", "-D", branch, cwd=store.repo, check=False)
    if local.returncode != 0:
        return f"left local {branch}: {git_reason(local.stderr)}"
    return ""


def opened_on_another_branch(store, entry, branch, stderr):
    """True when git says branch is absent and the entry's PR was opened from a different branch.

    An older queue opened the PR on landing/q<n> and never created
    landing/e<n>. The merged PR then settles without deleting that name.
    Only remote_branch_is_gone calls this, and only when no forge answers.
    A failed read leaves the entry."""
    if _CLIENT_ABSENT_REF.search(stderr or "") is None:
        return False
    view = gh("pr", "view", entry["pr"], "--json", "headRefName", "-q", ".headRefName", cwd=store.repo)
    head = (view.stdout or "").strip()
    return view.returncode == 0 and bool(head) and head != branch


def delete_queue_branch(store, entry):
    """Drop landing/e<n> after the PR has merged.

    Returns (deleted, warning). The branch is done when the server accepts
    the delete or when remote_branch_is_gone says it is gone. A local
    branch that exists and cannot be deleted is named in warning. The entry
    still lands when the remote ref is gone."""
    branch = human_branch(entry)
    pushed = git_push(store.contract["remote"], "--delete", branch, cwd=store.repo, check=False)
    if pushed.returncode != 0:
        stderr = pushed.stderr or ""
        if not remote_branch_is_gone(store, entry, branch, stderr):
            return False, ""
    return True, forget_local_branch(store, branch)


def entry_row(store, ident):
    return store.db.execute("SELECT * FROM entry WHERE id = ?", (ident,)).fetchone()


def read_pr_state(store, url):
    view = gh("pr", "view", url, "--json", "state,headRefOid,mergeCommit",
              "-q", '.state + " " + .headRefOid + " " + (.mergeCommit.oid // "")', cwd=store.repo)
    return (view.stdout.strip().split(" ") + ["", "", ""])[:3]


def take_pr(store, entry, landed, bounced):
    """Settle a merged or closed PR before a failed check can bounce it.

    Returns True when this poll should leave the entry alone."""
    state, head, merged = read_pr_state(store, entry["pr"])
    if state == "MERGED":
        deleted, warning = delete_queue_branch(store, entry)
        if not deleted:
            return True
        with store.tx() as db:
            if head == entry["candidate"]:
                settle_landed(store, db, entry["id"], merged, warning)
                outcome = "landed"
            else:
                settle_bounced(store, db, entry["id"], f"merged at {merged[:12]} with head {head[:12]}, not the checked "
                                                       f"{entry['candidate'][:12]}; review what reached trunk")
                outcome = "bounced"
            db.execute("INSERT OR REPLACE INTO contract VALUES ('tip', ?)", (json.dumps(merged),))
        (landed if outcome == "landed" else bounced).append(entry["id"])
        return True
    if state == "CLOSED":
        with store.tx() as db:
            settle_bounced(store, db, entry["id"], "PR closed without merging")
        bounced.append(entry["id"])
        return True
    if state == "OPEN" and head and head != entry["candidate"]:
        with store.tx() as db:
            store.set_entry(db, entry["id"], "awaiting-merge", note=f"PR head changed to {head[:12]} outside the queue")
        return True
    return False


def poll_human(store):
    landed, bounced, adopted, opened = [], [], [], []
    for entry in store.entries("awaiting-merge"):
        if not entry["pr"]:
            outcome = ensure_pr(store, entry)
            if outcome == "adopted":
                adopted.append(entry["id"])
            elif outcome == "created":
                opened.append(entry["id"])
            entry = entry_row(store, entry["id"])
        if take_pr(store, entry, landed, bounced):
            continue
        if store.contract["mode"] != "merge":
            continue
        if entry["note"] == MERGE_REQUESTED:
            blocker, detail, armed = merge_blocker(store, entry["pr"])
            if take_pr(store, entry, landed, bounced):
                continue
            if blocker == "failed":
                bounce_open_pr(store, entry["id"], entry["pr"], f"required checks failed on {entry['pr']}: {detail}", armed)
                bounced.append(entry["id"])
                continue
            if blocker == "review":
                pause_for_review(store, entry["pr"], detail, disarm=True, armed=armed)
            continue
        # A merge command can return before pr view reports MERGED.
        reads = 4 if request_merge(store, entry["id"], entry["pr"]) else 1
        entry = entry_row(store, entry["id"])
        if entry["state"] == "bounced":
            bounced.append(entry["id"])
            continue
        if entry["state"] != "awaiting-merge":
            continue
        for attempt in range(reads):
            if take_pr(store, entry, landed, bounced):
                break
            entry = entry_row(store, entry["id"])
            if entry["state"] != "awaiting-merge" or attempt + 1 == reads:
                break
            time.sleep(0.5)
    return landed, bounced, adopted, opened


def second_of(row):
    return row["b"] if row["first"] == row["a"] else row["a"]


def active_contests(db):
    """Open contests, and settled ones whose first holder has not landed an entry yet."""
    rows = db.execute("SELECT * FROM contest WHERE state IN ('open', 'settled') ORDER BY id").fetchall()
    return [row for row in rows if not contest_done(db, row)]


def contest_done(db, row):
    return row["state"] == "settled" and db.execute(
        "SELECT 1 FROM entry WHERE holder = ? AND state = 'landed'", (row["first"],)).fetchone() is not None


def held_holders(db):
    """Each held holder and the lowest active contest that holds it."""
    held = {}
    for row in active_contests(db):
        for holder in (row["a"], row["b"]) if row["state"] == "open" else (second_of(row),):
            held.setdefault(holder, row["id"])
    return held


def unheld_queued(store):
    held = held_holders(store.db)
    return [entry for entry in store.entries("queued") if entry["holder"] not in held]


def contest_id(text):
    if not re.fullmatch(r"C?\d+", text or ""):
        raise LandError(f"{text!r} is not a contest id such as C3")
    return int(text.lstrip("C"))


def contest(store, owner, holders=None, settle=None, first=None, cancel=None):
    """Every form waits for the queue lock, so a ruling never changes under a running land."""
    with open(store.dir / ".queue.lock", "a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        with store.tx() as db:
            check_ruling_owner(db, owner)
            if holders is not None:
                return open_contest(store, db, holders)
            if settle is not None:
                return settle_contest(store, db, contest_id(settle), first)
            return cancel_contest(store, db, contest_id(cancel))


def open_contest(store, db, holders):
    pair = [holder.strip() for holder in holders.split(",")]
    if len(pair) != 2 or not all(pair) or pair[0] == pair[1]:
        raise LandError("a contest needs two different holders")
    a, b = pair
    for row in active_contests(db):
        if {row["a"], row["b"]} == {a, b}:
            return f"C{row['id']}"
    started = db.execute("SELECT * FROM entry WHERE holder IN (?, ?) AND state IN ('landing', 'awaiting-merge', 'landed') "
                         "ORDER BY id LIMIT 1", (a, b)).fetchone()
    if started:
        raise LandError(f"{started['holder']} has {entry_label(started['id'])} {started['state']}; there is nothing left to order")
    cursor = db.execute("INSERT INTO contest (at, a, b, state) VALUES (?, ?, ?, 'open')", (stamp(), a, b))
    store.log(db, "contest", cursor.lastrowid, "open", f"{a},{b}")
    return f"C{cursor.lastrowid}"


def settle_contest(store, db, number, first):
    row = db.execute("SELECT * FROM contest WHERE id = ?", (number,)).fetchone()
    if not row:
        raise LandError(f"no C{number}")
    if row["state"] == "cancelled":
        raise LandError(f"C{number} is cancelled")
    if first not in (row["a"], row["b"]):
        raise LandError(f"{first} is not a holder in C{number}")
    second = row["b"] if first == row["a"] else row["a"]
    settled = f"C{number}: {first} lands first, {second} waits"
    if contest_done(db, row):
        if row["first"] == first:
            return settled
        raise LandError(f"C{number} is done: {row['first']} landed")
    if row["first"] and row["first"] != first:
        # An open PR can merge on its own, so an order that has started cannot be reversed.
        started = db.execute("SELECT * FROM entry WHERE holder = ? AND state IN ('landing', 'awaiting-merge') ORDER BY id LIMIT 1",
                             (row["first"],)).fetchone()
        if started:
            raise LandError(f"C{number} cannot put {first} first: {row['first']} has {entry_label(started['id'])} {started['state']}")
    edges = [(other["first"], second_of(other), other["id"]) for other in active_contests(db)
             if other["state"] == "settled" and other["id"] != number]
    cycle = sorted(ident for start, end, ident in edges if start in reach(edges, second) and first in reach(edges, end))
    if cycle:
        raise LandError(f"C{number} cannot order {first} before {second}: it closes a cycle with "
                        + ", ".join(f"C{ident}" for ident in cycle))
    if (row["state"], row["first"]) != ("settled", first):
        db.execute("UPDATE contest SET first = ?, state = 'settled' WHERE id = ?", (first, number))
        store.log(db, "contest", number, "settled", first)
    return settled


def reach(edges, start):
    """Every holder that must land after start, start included, under these first-to-second orders."""
    seen, todo = {start}, [start]
    while todo:
        node = todo.pop()
        for before, after, _ident in edges:
            if before == node and after not in seen:
                seen.add(after)
                todo.append(after)
    return seen


def cancel_contest(store, db, number):
    row = db.execute("SELECT state FROM contest WHERE id = ?", (number,)).fetchone()
    if not row:
        raise LandError(f"no C{number}")
    if row["state"] != "cancelled":
        db.execute("UPDATE contest SET state = 'cancelled' WHERE id = ?", (number,))
        store.log(db, "contest", number, "cancelled")
    return f"C{number} cancelled"


def land(store):
    handle = open(store.dir / ".queue.lock", "a")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return "queue busy: another run is landing and will take queued entries. Run land again later if entries stay queued."
    try:
        if store.contract.get("paused"):
            return f"queue paused: {store.contract['paused']}"
        reconcile(store)
        integration = Integration(store)
        landed, bounced, opened, adopted = [], [], [], []
        if store.contract["mode"] in ("human", "merge"):
            git("fetch", store.contract["remote"], store.contract["trunk"], cwd=store.repo)
            if rewound(store, git("rev-parse", trunk_ref(store.contract), cwd=store.repo).stdout.strip()):
                return report(store, [], [], [])
            if store.contract["mode"] == "merge":
                advance_drain(store)
            polled_landed, polled_bounced, polled_adopted, polled_opened = poll_human(store)
            landed.extend(polled_landed)
            bounced.extend(polled_bounced)
            adopted.extend(polled_adopted)
            opened.extend(polled_opened)
            for entry in unheld_queued(store):
                (opened if land_human(store, integration, entry) else bounced).append(entry["id"])
            if store.contract["mode"] == "merge" and opened:
                more_landed, more_bounced, more_adopted, more_opened = poll_human(store)
                landed.extend(more_landed)
                bounced.extend(more_bounced)
                adopted.extend(more_adopted)
                opened.extend(more_opened)
            states = {row["id"]: row["state"] for row in store.db.execute("SELECT id, state FROM entry")}
            bounced += [ident for ident in opened if states[ident] == "bounced" and ident not in bounced]
            opened = [ident for ident in opened if states[ident] == "awaiting-merge"]
            return report(store, landed, bounced, opened, adopted)
        single, rounds = False, 0
        while (queued := unheld_queued(store)) and not store.contract.get("paused"):
            rounds += 1
            if rounds > 4 * len(queued) + 4:
                break
            size = 1 if single else max(1, int(store.contract.get("batch") or 1))
            done, out, requeued, _ = attempt(store, integration, queued[:size])
            landed += done
            bounced += out
            single = bool(requeued)
        return report(store, landed, bounced, opened)
    except Infrastructure as problem:
        with store.tx() as db:
            for entry in db.execute("SELECT id FROM entry WHERE state = 'landing'").fetchall():
                store.set_entry(db, entry["id"], "queued", candidate="", note=str(problem))
        if isinstance(problem, AutoMergeStillEnabled):
            pause(store, str(problem))
        else:
            suggestion = suggested_merge_method(store.repo, str(problem))
            if suggestion:
                pause(store, f"{problem}. Run land.py mode merge --merge-method {suggestion}, then land.py resume")
            else:
                pause(store, f"{problem}. Fix it, then run land.py resume")
        return report(store, [], [], [])
    finally:
        handle.close()


def report(store, landed, bounced, opened, adopted=()):
    rows = {row["id"]: row for row in store.db.execute("SELECT * FROM entry")}
    lines = []
    if landed:
        parts = []
        for i in landed:
            text = f"{entry_label(i)} ({rows[i]['holder']})"
            if rows[i]["note"].startswith("left local "):
                text += f": {rows[i]['note']}"
            parts.append(text)
        lines.append("landed " + ", ".join(parts))
    if opened:
        lead = "opened PRs that merge when their checks pass: " if store.contract["mode"] == "merge" else "opened PRs for "
        lines.append(lead + ", ".join(f"{entry_label(i)} ({rows[i]['holder']}) {rows[i]['pr']}" for i in opened))
    lines += [f"adopted {entry_label(i)} ({rows[i]['holder']}) {rows[i]['pr']}" for i in adopted]
    lines += [f"bounced {entry_label(i)} ({rows[i]['holder']}): {rows[i]['note']}" for i in bounced]
    held = held_holders(store.db)
    waiting = []
    for row in rows.values():
        hold = held.get(row["holder"]) if row["state"] == "queued" else None
        if row["state"] in ("queued", "landing"):
            waiting.append(entry_label(row["id"]) + (f" (held by C{hold})" if hold else ""))
    if waiting:
        lines.append("still queued: " + ", ".join(waiting))
    if store.contract.get("paused"):
        lines.append(f"queue paused: {store.contract['paused']}")
    return "\n".join(lines) or "nothing to land"


def holder_status(store, holder, sha=None):
    """Entries of one holder, or of every holder under a prefix that ends in /, optionally only those at one commit."""
    if sha:
        # submit stores the full SHA rev-parse gives, so a short or uppercase SHA compares the same way.
        resolved = git("rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}", cwd=store.repo, check=False)
        sha = resolved.stdout.strip() if resolved.returncode == 0 else sha.lower()
    lines = []
    for row in store.db.execute("SELECT * FROM entry ORDER BY id"):
        if row["holder"] != holder and not (holder.endswith("/") and row["holder"].startswith(holder)):
            continue
        if sha and row["sha"] != sha:
            continue
        line = f"{entry_label(row['id'])} {row['state']} ({row['holder']}, {row['sha'][:12]})"
        if row["state"] == "landed" and row["landed"]:
            line += f" as {row['landed'][:12]}"
        elif row["state"] == "awaiting-merge" and row["pr"]:
            line += f" {row['pr']}"
        elif row["state"] == "bounced":
            line += f": {row['note']}"
        lines.append(line)
    return "\n".join(lines) or f"no entries held by {holder}" + (f" at {sha}" if sha else "")


def status(store, ident=None):
    if ident:
        number = entry_id(ident)
        row = store.db.execute("SELECT * FROM entry WHERE id = ?", (number,)).fetchone()
        if not row:
            raise LandError(f"no {entry_label(number)}")
        detail = [f"landed as {row['landed'][:12]}" if row["landed"] else "", row["pr"], row["note"]]
        return f"{entry_label(row['id'])} {row['state']} ({row['holder']}, {row['branch']})" + "".join(f". {part}" for part in detail if part)
    states = dict(store.db.execute("SELECT state, count(*) FROM entry GROUP BY state").fetchall())
    live = in_flight(store.db)
    leases = len(live)
    reserved = sum(counts(row, live) for row in standing(store.db))
    contract = store.contract
    parts = [f"{state}: {n}" for state, n in states.items()] + ([f"leases held: {leases}"] if leases else [])
    if contract.get("cap"):
        parts.append(f"changes in flight: {leases + reserved} of {contract['cap']}")
    paused = f" Paused: {contract['paused']}" if contract.get("paused") else ""
    return f"{contract['mode']} mode onto {trunk_ref(contract)}. " + (", ".join(parts) or "empty") + "." + paused


def parser():
    top = argparse.ArgumentParser(prog="land.py", description=__doc__.splitlines()[0])
    top.add_argument("--repo", default=".", help="any checkout of the repository (default: current directory)")
    sub = top.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="write the repository's landing contract")
    p.add_argument("--trunk", required=True, help="branch on the remote, or a lane name in local mode")
    p.add_argument("--mode", choices=MODES + tuple(LEGACY_MODES), required=True,
                   help="human: PRs you merge; merge: PRs the queue merges; push: no PRs, the queue pushes trunk; local: a lane ref")
    p.add_argument("--remote", default="origin")
    p.add_argument("--base", default="", help="local mode: the commit the lane starts from")
    p.add_argument("--check", action="append", default=[], help="command that must pass before landing; repeatable")
    p.add_argument("--setup", default="", help="command run before checks in the clean integration worktree, such as npm ci")
    p.add_argument("--batch", type=int, default=1, help="entries checked together; a failed batch lands one at a time")
    p.add_argument("--timeout", type=int, default=1800, help="seconds before a check is killed")
    p.add_argument("--merge-method", choices=MERGE_METHODS, default=None,
                   help="merge mode: how the queue merges its PRs, checked against the repository whenever it is set. "
                        "omitted in merge mode, init stores the one allowed method, or merge when gh cannot say")
    p.add_argument("--cap", type=int, help="most changes in flight on the repository at once; 0 clears it")

    p = sub.add_parser("cap", help="set the most changes in flight on the repository at once; 0 clears it")
    p.add_argument("count", type=int)

    mode_help = "switch human, merge, or push when the queue is empty. --merge-method may change while entries are in flight"
    p = sub.add_parser("mode", help=mode_help, description=mode_help)
    p.add_argument("mode", choices=MODES + tuple(LEGACY_MODES))
    p.add_argument("--merge-method", choices=MERGE_METHODS)

    owner_help = "<holder prefix>@<generation> of the coordinator writing; refused below that prefix's floor"
    ruling_help = "<prefix>@<generation> of the writer, such as .admin/@2; refused below that prefix's floor"
    p = sub.add_parser("owner", help="raise a holder prefix's generation floor; it never lowers")
    p.add_argument("--prefix", required=True, help="a holder prefix ending in /, such as docs/")
    p.add_argument("--generation", type=int, required=True)

    p = sub.add_parser("lease", help="claim, renew, release, or list path leases")
    t = p.add_subparsers(dest="action", required=True)
    a = t.add_parser("claim")
    a.add_argument("--holder", required=True)
    a.add_argument("--paths", required=True, help="comma-separated files or directories; . is the whole repository")
    a.add_argument("--ttl-hours", type=float, default=6)
    a.add_argument("--owner", help=owner_help)
    a = t.add_parser("renew")
    a.add_argument("id")
    a.add_argument("--ttl-hours", type=float, default=6)
    a.add_argument("--if-live", action="store_true", help="refuse when the lease has expired instead of admitting it again")
    a.add_argument("--owner", help=owner_help)
    a = t.add_parser("release")
    a.add_argument("id")
    a.add_argument("--owner", help=owner_help)
    t.add_parser("list")
    a = t.add_parser("check", help="print what a claim would answer now; claims no lease and arms no reservation")
    a.add_argument("--holder", required=True)
    a.add_argument("--paths", required=True)
    a = t.add_parser("reserve", help="reserve paths for a holder prefix by a ruling; prints S<n>")
    a.add_argument("--for", dest="prefix", required=True, help="the winner's holder prefix, such as docs/")
    a.add_argument("--paths", required=True, help="comma-separated files or directories")
    a.add_argument("--ruling", required=True, help="the ruling this carries out, such as R4; a rerun returns the same S<n>")
    a.add_argument("--ttl-hours", type=float, default=2, help="hours the reservation stands once it arms")
    a.add_argument("--owner", required=True, help=ruling_help)
    a = t.add_parser("unreserve", help="lift a reservation")
    a.add_argument("id")
    a.add_argument("--owner", required=True, help=ruling_help)

    p = sub.add_parser("submit", help="queue a reviewed commit for landing")
    p.add_argument("--holder", required=True)
    p.add_argument("--branch", required=True)
    p.add_argument("--sha", required=True, help="the exact SHA the review passed")
    p.add_argument("--lease", required=True)
    p.add_argument("--reviewer", required=True, help="provider/model of the reviewer that passed this SHA")
    p.add_argument("--title", default="", help="human mode: the PR title (default: the last commit subject)")
    p.add_argument("--body-file", default="", help="human mode: a file holding the PR body")
    p.add_argument("--owner", help=owner_help)

    p = sub.add_parser("share", help="set a holder prefix's share of the cap")
    p.add_argument("--for", dest="prefix", required=True, help="a holder prefix ending in /, such as docs/")
    p.add_argument("count", type=int)
    p.add_argument("--clear", action="store_true", help="remove the share; pass 0")
    p.add_argument("--owner", required=True, help=ruling_help)

    p = sub.add_parser("contest", help="hold two holders' entries, then order them; waits for a running land")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--holders", help="<a>,<b>: hold both holders' entries until settled; prints C<n>")
    g.add_argument("--settle", help="C<n>: with --first, land the first holder before the other")
    g.add_argument("--cancel", help="C<n>: remove the hold or the order")
    p.add_argument("--first", help="with --settle, the holder that lands first")
    p.add_argument("--owner", required=True, help=ruling_help)

    sub.add_parser("land", help="drain the queue unless another run holds it")
    sub.add_parser("resume", help="clear a pause after you checked trunk")
    p = sub.add_parser("status")
    p.add_argument("id", nargs="?")
    p.add_argument("--holder", help="list this holder's entries; a value ending in / matches every holder under it")
    p.add_argument("--sha", help="with --holder, only entries at exactly this commit")
    p = sub.add_parser("slot", help="run a heavy command under a governor slot")
    p.add_argument("--exclusive", action="store_true", help="hold every slot: for benchmarks that need a quiet machine")
    p.add_argument("cmd", nargs=argparse.REMAINDER)
    return top


def run(argv):
    args = parser().parse_args(argv)
    if args.command == "slot":
        command = args.cmd[1:] if args.cmd[:1] == ["--"] else args.cmd
        if not command:
            raise LandError("slot needs a command after --")
        with (exclusive_slot() if args.exclusive else slot()):
            return None, subprocess.run(command).returncode
    if args.command == "init":
        return init(args.repo, args.trunk, args.mode, args.remote, args.base, args.check, args.setup, args.batch, args.timeout,
                    args.merge_method, args.cap), 0
    store = Store.for_repo(args.repo)
    if args.command == "cap":
        return change_cap(store, args.count), 0
    if args.command == "owner":
        return raise_floor(store, args.prefix, args.generation), 0
    if args.command == "lease":
        if args.action == "claim":
            return lease_claim(store, args.holder, args.paths, args.ttl_hours, args.owner), 0
        if args.action == "check":
            return lease_check(store, args.holder, args.paths)
        if args.action == "list":
            return lease_list(store), 0
        if args.action == "reserve":
            return lease_reserve(store, args.prefix, args.paths, args.ruling, args.ttl_hours, args.owner), 0
        if args.action == "unreserve":
            return lease_unreserve(store, reservation_id(args.id), args.owner), 0
        number = lease_id(args.id)
        if args.action == "renew":
            return lease_renew(store, number, args.ttl_hours, args.if_live, args.owner), 0
        return lease_release(store, number, args.owner), 0
    if args.command == "mode":
        return change_mode(store, args.mode, args.merge_method), 0
    if args.command == "share":
        return change_share(store, args.prefix, args.count, args.clear, args.owner), 0
    if args.command == "contest":
        if (args.settle is None) != (args.first is None):
            raise LandError("--settle and --first go together")
        return contest(store, args.owner, args.holders, args.settle, args.first, args.cancel), 0
    if args.command == "submit":
        body = Path(args.body_file).read_text() if args.body_file else ""
        return submit(store, args.holder, args.branch, args.sha, args.lease, args.reviewer, args.title, body, args.owner), 0
    if args.command == "land":
        return land(store), 0
    if args.command == "resume":
        with store.tx() as db:
            db.execute("INSERT OR REPLACE INTO contract VALUES ('paused', '\"\"')")
            db.execute("DELETE FROM contract WHERE key = 'tip'")
            store.log(db, "queue", 0, "resumed")
        return "queue resumed", 0
    if args.holder:
        if args.id:
            raise LandError("status takes an entry id or --holder, not both")
        return holder_status(store, args.holder, args.sha), 0
    if args.sha:
        raise LandError("status --sha needs --holder")
    return status(store, args.id), 0


def main(argv=None):
    try:
        output, code = run(sys.argv[1:] if argv is None else argv)
    except LandError as error:
        print(f"land: {error}", file=sys.stderr)
        return 1
    if output is not None:
        print(output)
    return code


if __name__ == "__main__":
    sys.exit(main())
