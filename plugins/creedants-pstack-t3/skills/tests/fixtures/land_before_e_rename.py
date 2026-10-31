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
SCHEMA = """
CREATE TABLE IF NOT EXISTS contract (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS lease (
  id INTEGER PRIMARY KEY, at TEXT NOT NULL, holder TEXT NOT NULL, paths TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('active', 'submitted', 'released')), expires TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS entry (
  id INTEGER PRIMARY KEY, at TEXT NOT NULL, holder TEXT NOT NULL, branch TEXT NOT NULL,
  sha TEXT NOT NULL, base TEXT NOT NULL, fingerprint TEXT NOT NULL, lease INTEGER NOT NULL REFERENCES lease(id),
  reviewer TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('queued', 'landing', 'awaiting-merge', 'landed', 'bounced')),
  candidate TEXT NOT NULL DEFAULT '', landed TEXT NOT NULL DEFAULT '', pr TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT '', UNIQUE (sha, holder));
CREATE TABLE IF NOT EXISTS attempt (
  id INTEGER PRIMARY KEY, at TEXT NOT NULL, base TEXT NOT NULL, candidate TEXT NOT NULL,
  entries TEXT NOT NULL, state TEXT NOT NULL CHECK (state IN ('publishing', 'published', 'abandoned')));
CREATE TABLE IF NOT EXISTS log (at TEXT NOT NULL, kind TEXT NOT NULL, id INTEGER NOT NULL, state TEXT NOT NULL, note TEXT NOT NULL);
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


def trunk_ref(contract):
    if contract["mode"] == "local":
        return f"refs/landing/{contract['trunk']}"
    return f"refs/remotes/{contract['remote']}/{contract['trunk']}"


def init(path, trunk, mode, remote, base, checks, setup, batch, timeout, merge_method="merge"):
    mode = LEGACY_MODES.get(mode, mode)
    common = common_dir(path)
    repo = common.parent if common.name == ".git" else Path(git("rev-parse", "--show-toplevel", cwd=path).stdout.strip())
    directory = state_home() / "landing" / store_name(common)
    directory.mkdir(parents=True, exist_ok=True)
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
    if mode == "local" and git("rev-parse", "--verify", "--quiet", trunk_ref(wanted), cwd=repo, check=False).returncode != 0:
        if not base:
            raise LandError(f"local mode lands on {trunk_ref(wanted)}; pass --base <commit> to create it")
        git("update-ref", trunk_ref(wanted), git("rev-parse", "--verify", f"{base}^{{commit}}", cwd=repo).stdout.strip(), "", cwd=repo)
    return f"{'updated' if current else 'created'} {directory}"


def change_mode(store, mode, merge_method):
    """Switch between the remote modes while nothing is in flight. Local mode lands on a different ref, so it needs its own contract."""
    mode = LEGACY_MODES.get(mode, mode)
    current = store.contract["mode"]
    if "local" in (mode, current) and mode != current:
        raise LandError("local mode lands on refs/landing/<trunk>, not the remote trunk; switching to or from it needs a new contract")
    with store.tx() as db:
        busy = db.execute("SELECT count(*) FROM entry WHERE state IN ('queued', 'landing', 'awaiting-merge')").fetchone()[0]
        if busy:
            raise LandError(f"{busy} entries are queued, landing, or awaiting merge; change the mode when the queue is empty")
        db.execute("INSERT OR REPLACE INTO contract VALUES ('mode', ?)", (json.dumps(mode),))
        if merge_method:
            db.execute("INSERT OR REPLACE INTO contract VALUES ('mergeMethod', ?)", (json.dumps(merge_method),))
        store.log(db, "queue", 0, f"mode {mode}", f"was {current}")
    return f"landing mode is now {mode}" + (f", merging with --{merge_method}" if merge_method else "")


def lease_claim(store, holder, paths, ttl_hours):
    wanted = sorted({canonical(p) for p in paths.split(",")})
    with store.tx() as db:
        rows = db.execute("SELECT * FROM lease WHERE state != 'released' AND holder != ? AND (state = 'submitted' OR expires > ?)",
                          (holder, stamp())).fetchall()
        clash = [row for row in rows if overlaps(wanted, row["paths"].split("\n"))]
        if clash:
            raise LandError("paths overlap " + "; ".join(f"L{row['id']} held by {row['holder']} on {row['paths'].replace(chr(10), ', ') or '(whole repo)'}" for row in clash))
        cursor = db.execute("INSERT INTO lease (at, holder, paths, state, expires) VALUES (?, ?, ?, 'active', ?)",
                            (stamp(), holder, "\n".join(wanted), stamp(now() + timedelta(hours=ttl_hours))))
        store.log(db, "lease", cursor.lastrowid, "active", holder)
    return f"L{cursor.lastrowid}"


def lease_id(text):
    if not re.fullmatch(r"L?\d+", text or ""):
        raise LandError(f"{text!r} is not a lease id such as L3")
    return int(text.lstrip("L"))


def submit(store, holder, branch, sha, lease, reviewer, title="", body=""):
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
        existing = db.execute("SELECT id, state FROM entry WHERE sha = ? AND holder = ?", (sha, holder)).fetchone()
        if existing and existing["state"] != "bounced":
            return f"Q{existing['id']} already {existing['state']}"
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
    return f"Q{cursor.lastrowid}"


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
    db.execute("UPDATE lease SET state = 'released' WHERE id = ?", (lease,))
    store.log(db, "lease", lease, "released", f"Q{ident} landed")


def settle_bounced(store, db, ident, reason):
    """A bounced entry gives its lease back to the holder for the fix, with a fresh expiry."""
    forget_absent(db, ident)
    lease = db.execute("SELECT lease FROM entry WHERE id = ?", (ident,)).fetchone()["lease"]
    store.set_entry(db, ident, "bounced", note=reason, candidate="")
    db.execute("UPDATE lease SET state = 'active', expires = ? WHERE id = ?", (stamp(now() + timedelta(hours=6)), lease))
    store.log(db, "lease", lease, "active", f"Q{ident} bounced; the lease is back for the fix")


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
        with store.tx() as db:
            if reason == "already-in-trunk":
                settle_landed(store, db, entry["id"], base, "already in trunk")
                landed.append(entry["id"])
            elif reason:
                settle_bounced(store, db, entry["id"], reason)
                bounced.append(entry["id"])
            else:
                store.set_entry(db, entry["id"], "landing", candidate=integration.head())
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
    integration.reset(git("rev-parse", trunk_ref(contract), cwd=store.repo).stdout.strip())
    reason = integration.apply(entry)
    if not reason:
        reason = integration.check()
        reason = f"checks failed: {reason}" if reason else None
    if reason == "already-in-trunk":
        with store.tx() as db:
            settle_landed(store, db, entry["id"], integration.head(), "already in trunk")
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
    return f"landing/q{entry['id']}"


def ensure_pr(store, entry):
    """Adopt the PR for the entry's branch, or open it. A crash between push and PR creation is safe to rerun."""
    contract = store.contract
    view = gh("pr", "view", human_branch(entry), "--json", "url", "-q", ".url", cwd=store.repo)
    url = view.stdout.strip() if view.returncode == 0 else ""
    if not url:
        title = entry["title"] or git("log", "-1", "--format=%s", entry["sha"], cwd=store.repo).stdout.strip()
        receipt = f"Queued by {entry['holder']} from `{entry['branch']}`. Reviewed by {entry['reviewer']} at {entry['sha']}."
        body = f"{entry['body'].rstrip()}\n\n{receipt}" if entry["body"] else receipt
        created = gh("pr", "create", "--base", contract["trunk"], "--head", human_branch(entry), "--title", title, "--body", body, cwd=store.repo)
        if created.returncode != 0:
            raise Infrastructure("gh pr create failed: " + created.stderr.strip())
        url = created.stdout.strip().splitlines()[-1]
    with store.tx() as db:
        store.set_entry(db, entry["id"], "awaiting-merge", pr=url, note="")
    if contract["mode"] == "merge":
        request_merge(store, entry["id"], url)
    return True


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
    """Bounce an open merge-mode PR. Disable auto-merge when it is on, and leave the PR open."""
    problem = disarm_auto_merge(store, url, armed)
    if problem:
        reason = f"{reason} (auto-merge still enabled: {problem})"
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


def remote_branch_is_gone(store, branch, stderr):
    """Whether a failed delete left the queue branch absent.

    Merge and human mode ask the forge only when the contract remote has
    exactly one push URL and that URL names the same owner/repo gh resolves.
    Any other push setup, or a repo read that fails, leaves the entry.
    Only HTTP 404 counts as gone. Push and local mode have no forge read.
    They accept only that exact client line, and any other failure waits
    for the next run."""
    if store.contract["mode"] in ("merge", "human"):
        if not forge_is_only_push_target(store):
            return False
        return forge_branch_status(store.repo, branch) == 404
    return _CLIENT_ABSENT_REF.search(stderr or "") is not None


def delete_queue_branch(store, entry):
    """Drop landing/q<n> after the PR has merged.

    Returns (deleted, warning). The delete counts as done when the server
    accepts it, or when remote_branch_is_gone says the branch is gone.
    A local branch that exists and cannot be deleted is named in warning.
    The entry still lands when the remote ref is gone."""
    branch = human_branch(entry)
    remote = store.contract["remote"]
    pushed = git_push(remote, "--delete", branch, cwd=store.repo, check=False)
    if pushed.returncode != 0 and not remote_branch_is_gone(store, branch, pushed.stderr or ""):
        return False, ""
    git("update-ref", "-d", f"refs/remotes/{remote}/{branch}", cwd=store.repo, check=False)
    warning = ""
    if git("show-ref", "--verify", "--quiet", f"refs/heads/{branch}", cwd=store.repo, check=False).returncode == 0:
        local = git("branch", "-D", branch, cwd=store.repo, check=False)
        if local.returncode != 0:
            warning = f"left local {branch}: {git_reason(local.stderr)}"
    return True, warning


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
    landed, bounced = [], []
    for entry in store.entries("awaiting-merge"):
        if not entry["pr"]:
            ensure_pr(store, entry)
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
    return landed, bounced


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
        landed, bounced, opened = [], [], []
        if store.contract["mode"] in ("human", "merge"):
            git("fetch", store.contract["remote"], store.contract["trunk"], cwd=store.repo)
            if rewound(store, git("rev-parse", trunk_ref(store.contract), cwd=store.repo).stdout.strip()):
                return report(store, [], [], [])
            if store.contract["mode"] == "merge":
                advance_drain(store)
            landed, bounced = poll_human(store)
            for entry in store.entries("queued"):
                (opened if land_human(store, integration, entry) else bounced).append(entry["id"])
            if store.contract["mode"] == "merge" and opened:
                more_landed, more_bounced = poll_human(store)
                landed, bounced = landed + more_landed, bounced + more_bounced
            states = {row["id"]: row["state"] for row in store.db.execute("SELECT id, state FROM entry")}
            bounced += [ident for ident in opened if states[ident] == "bounced" and ident not in bounced]
            opened = [ident for ident in opened if states[ident] == "awaiting-merge"]
            return report(store, landed, bounced, opened)
        single, rounds = False, 0
        while (queued := store.entries("queued")) and not store.contract.get("paused"):
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
        pause(store, f"{problem}. Fix it, then run land.py resume")
        return report(store, [], [], [])
    finally:
        handle.close()


def report(store, landed, bounced, opened):
    rows = {row["id"]: row for row in store.db.execute("SELECT * FROM entry")}
    lines = []
    if landed:
        parts = []
        for i in landed:
            text = f"Q{i} ({rows[i]['holder']})"
            if rows[i]["note"].startswith("left local "):
                text += f": {rows[i]['note']}"
            parts.append(text)
        lines.append("landed " + ", ".join(parts))
    if opened:
        lead = "opened PRs that merge when their checks pass: " if store.contract["mode"] == "merge" else "opened PRs for "
        lines.append(lead + ", ".join(f"Q{i} ({rows[i]['holder']}) {rows[i]['pr']}" for i in opened))
    lines += [f"bounced Q{i} ({rows[i]['holder']}): {rows[i]['note']}" for i in bounced]
    waiting = [f"Q{row['id']}" for row in rows.values() if row["state"] in ("queued", "landing")]
    if waiting:
        lines.append("still queued: " + ", ".join(waiting))
    if store.contract.get("paused"):
        lines.append(f"queue paused: {store.contract['paused']}")
    return "\n".join(lines) or "nothing to land"


def status(store, ident=None):
    if ident:
        row = store.db.execute("SELECT * FROM entry WHERE id = ?", (int(ident.lstrip("Q")),)).fetchone()
        if not row:
            raise LandError(f"no {ident}")
        detail = [f"landed as {row['landed'][:12]}" if row["landed"] else "", row["pr"], row["note"]]
        return f"Q{row['id']} {row['state']} ({row['holder']}, {row['branch']})" + "".join(f". {part}" for part in detail if part)
    counts = dict(store.db.execute("SELECT state, count(*) FROM entry GROUP BY state").fetchall())
    leases = store.db.execute("SELECT count(*) FROM lease WHERE state = 'submitted' OR (state = 'active' AND expires > ?)", (stamp(),)).fetchone()[0]
    contract = store.contract
    parts = [f"{state}: {count}" for state, count in counts.items()] + ([f"leases held: {leases}"] if leases else [])
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
    p.add_argument("--merge-method", choices=MERGE_METHODS, default="merge", help="merge mode: how the queue merges its PRs")

    p = sub.add_parser("mode", help="switch between human, merge, and push while nothing is in flight")
    p.add_argument("mode", choices=MODES + tuple(LEGACY_MODES))
    p.add_argument("--merge-method", choices=MERGE_METHODS)

    p = sub.add_parser("lease", help="claim, renew, release, or list path leases")
    t = p.add_subparsers(dest="action", required=True)
    a = t.add_parser("claim")
    a.add_argument("--holder", required=True)
    a.add_argument("--paths", required=True, help="comma-separated files or directories; . is the whole repository")
    a.add_argument("--ttl-hours", type=float, default=6)
    a = t.add_parser("renew")
    a.add_argument("id")
    a.add_argument("--ttl-hours", type=float, default=6)
    a = t.add_parser("release")
    a.add_argument("id")
    t.add_parser("list")

    p = sub.add_parser("submit", help="queue a reviewed commit for landing")
    p.add_argument("--holder", required=True)
    p.add_argument("--branch", required=True)
    p.add_argument("--sha", required=True, help="the exact SHA the review passed")
    p.add_argument("--lease", required=True)
    p.add_argument("--reviewer", required=True, help="provider/model of the reviewer that passed this SHA")
    p.add_argument("--title", default="", help="human mode: the PR title (default: the last commit subject)")
    p.add_argument("--body-file", default="", help="human mode: a file holding the PR body")

    sub.add_parser("land", help="drain the queue unless another run holds it")
    sub.add_parser("resume", help="clear a pause after you checked trunk")
    p = sub.add_parser("status")
    p.add_argument("id", nargs="?")
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
                    args.merge_method), 0
    store = Store.for_repo(args.repo)
    if args.command == "lease":
        if args.action == "claim":
            return lease_claim(store, args.holder, args.paths, args.ttl_hours), 0
        if args.action == "list":
            rows = store.db.execute("SELECT * FROM lease WHERE state = 'submitted' OR (state = 'active' AND expires > ?) ORDER BY id", (stamp(),))
            return "\n".join(f"L{r['id']} {r['state']} {r['holder']} until {r['expires'][:16]}: {r['paths'].replace(chr(10), ', ') or '(whole repo)'}" for r in rows) or "no leases held", 0
        number = lease_id(args.id)
        with store.tx() as db:
            row = db.execute("SELECT state FROM lease WHERE id = ?", (number,)).fetchone()
            if not row or row["state"] != "active":
                raise LandError(f"L{number} is not active; a submitted lease is released when its entry lands or bounces")
            if args.action == "renew":
                db.execute("UPDATE lease SET expires = ? WHERE id = ?", (stamp(now() + timedelta(hours=args.ttl_hours)), number))
            else:
                db.execute("UPDATE lease SET state = 'released' WHERE id = ?", (number,))
            store.log(db, "lease", number, "renewed" if args.action == "renew" else "released")
        return f"L{number} {'renewed' if args.action == 'renew' else 'released'}", 0
    if args.command == "mode":
        return change_mode(store, args.mode, args.merge_method), 0
    if args.command == "submit":
        body = Path(args.body_file).read_text() if args.body_file else ""
        return submit(store, args.holder, args.branch, args.sha, args.lease, args.reviewer, args.title, body), 0
    if args.command == "land":
        return land(store), 0
    if args.command == "resume":
        with store.tx() as db:
            db.execute("INSERT OR REPLACE INTO contract VALUES ('paused', '\"\"')")
            db.execute("DELETE FROM contract WHERE key = 'tip'")
            store.log(db, "queue", 0, "resumed")
        return "queue resumed", 0
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
