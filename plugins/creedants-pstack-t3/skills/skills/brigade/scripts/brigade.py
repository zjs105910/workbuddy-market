#!/usr/bin/env python3
"""Bookkeeping for brigade restaurants.

A restaurant is one directory under the brigade store. Its tables hold current
state and log.tsv holds every change, so a report can say what is new since
the last one. The head chef thread is the only writer.

Kitchen words name files and commands. Output is plain engineering prose.
"""

import argparse
import fcntl
import functools
import json
import os
import re
import runpy
import shlex
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

TICKET_STATES = ("waiting", "assigned", "moved", "done", "dropped")
LIVE_TICKET_STATES = ("waiting", "assigned")
DISH_STATES = ("in-progress", "in-review", "passed", "sent-back", "blocked", "queued", "merged", "dropped")
COUNTED_STATES = ("in-progress", "in-review")
# A dish in one of these holds an active lease that watch keeps renewing. A queued dish's lease is the queue's.
LEASED_STATES = ("in-progress", "in-review", "passed", "sent-back", "blocked")
OPEN_LINES = {"in-review": "in review", "passed": "passed, not submitted", "sent-back": "sent back", "blocked": "parked"}
VERDICTS = {"pass": "passed", "send-back": "sent-back", "blocked": "blocked"}
MODES = ("full", "light")
ROUND_BUDGET = 3
OWING_STATES = ("in-progress", "in-review", "sent-back", "blocked")
ROUND_DECISIONS = ("known limits", "redesign", "drop")
ROUND_PARKED = "keep parked"
ROUND_KIND = "round-budget"
OPEN_RUN_MINUTES = 10

TABLES = {
    "rail.tsv": ("id", "at", "state", "source", "ref", "dish", "summary"),
    "dishes.tsv": ("id", "at", "state", "station", "tickets", "task", "thread", "branch", "pr", "sha", "summary", "timebox", "lease", "paths", "reported"),
    "pass.tsv": ("at", "dish", "pr", "sha", "verdict", "author", "verifier", "note", "report", "member"),
    "86.tsv": ("id", "at", "state", "dish", "question", "options", "default", "answer", "kind", "answered"),
    "log.tsv": ("at", "kind", "id", "state", "note"),
    # Only the executive admin's store has this table.
    "rulings.tsv": ("id", "at", "kind", "parties", "question", "rule", "decision", "supersedes", "state"),
}
ADDED_COLUMNS = {"pass.tsv": 2, "86.tsv": 2}
PREFIX = {"rail.tsv": "T", "dishes.tsv": "D", "86.tsv": "Q", "rulings.tsv": "R"}
ADMIN_DIR = ".admin"
ADMIN_NAME = "executive admin"
WORK_COMMANDS = ("fire", "brief", "dish", "pass", "watch")
ADMIN_COMMANDS = ("request", "rule", "sync")
RULING_KINDS = ("contested-paths", "ownership", "shares", "queue-order")
RULING_RULES = ("purpose", "priority", "age", "related-work", "dependency", "floor", "user")
RULING_STATES = ("in-force", "done", "expired", "superseded", "overruled")
NOT_STOPPED = "the old run has not been confirmed stopped; wait for it with t3_thread_wait, then pass --stopped <run id>"
NOTHING_HANDED = "nothing handed to you"
SNAPSHOT_CHUNK = 1 << 16
REVIEW_FILE = re.compile(r"(D\d+)-review(-.+)?\.md")
ITEM_REPORT = re.compile(r"(D\d+)\.md")
# A report shows each ticket and dish once, under the latest state it reached since the last report.
SECTIONS = {
    ("dish", "merged"): "Merged",
    ("dish", "passed"): "Passed review, not submitted",
    ("dish", "queued"): "Waiting to land",
    ("dish", "sent-back"): "Sent back after review",
    ("dish", "blocked"): "Blocked",
    ("mode", "full"): "Moved to full mode",
    ("dish", "in-progress"): "In progress",
    ("dish", "in-review"): "In progress",
    ("ticket", "waiting"): "New tickets, not started",
    ("ticket", "moved"): "Handed to another coordinator",
    ("dish", "dropped"): "Dropped",
    ("ticket", "dropped"): "Dropped",
}

MENU = """# Menu: {restaurant}

## Purpose

What this restaurant exists to achieve, in one or two sentences.

## What good looks like

Checkable outcomes, one per line.

## Off the menu

Work this restaurant does not take, even when asked.

## Budget

Any cap on parallel workers, and whether a provider's usage limit switches this restaurant to light mode.
"""

ADMIN_MENU = """# Menu: {restaurant}

## Purpose

Keep the user up to date across every coordinator on this repository, route the user's requests, and settle conflicts between coordinators by published rules.

## Priorities

Coordinator names, highest first, one per line. Only the user changes this list.

## Off the menu

Writing code, landing work, and every decision that belongs to the user: the repository cap, the landing mode, priorities, and purposes.
"""

HOUSE_RULES = """# House rules: {restaurant}

Paste these into every brief verbatim.

1. Write in plain engineering prose. brigade's kitchen terms name its files and commands only. Never use them in replies, reports, commits, or PRs.
2. Work lands only through the repository's landing queue (the landing skill). Workers never merge, rebase shared branches, or push trunk.
"""


class BrigadeError(Exception):
    pass


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def slug(text):
    value = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if not value:
        raise BrigadeError(f"cannot make a slug from {text!r}")
    return value


def store_root(flag=None):
    if flag:
        return Path(flag)
    if os.environ.get("BRIGADE_STORE"):
        return Path(os.environ["BRIGADE_STORE"])
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local/state")
    return Path(base) / "pstack-t3" / "brigade"


def clean(value):
    return re.sub(r"[\t\r\n]+", " ", str(value if value is not None else "")).strip()


def write_atomic(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, suffix=".tmp") as handle:
        try:
            handle.write(text)
        except BaseException:
            handle.close()
            os.unlink(handle.name)
            raise
    os.replace(handle.name, path)


def is_timestamp(value):
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return "T" in value


def parse_row(table, line):
    """One complete line of a table as a row, or None when its field count or timestamp is wrong.

    A row written before a table gained its `ADDED_COLUMNS` is read padded and never rewritten.
    """
    header = TABLES[table]
    fields = line.split("\t")
    missing = len(header) - len(fields)
    if not 0 <= missing <= ADDED_COLUMNS.get(table, 0) or not is_timestamp(fields[header.index("at")]):
        return None
    return dict(zip(header, fields + [""] * missing))


def read_chunk(fd):
    return os.read(fd, SNAPSHOT_CHUNK)


def is_admin(meta):
    return meta.get("role") == "admin"


def holder_prefix(meta):
    """The landing holder prefix of a store: `.admin/` for the executive admin, else the restaurant's slug."""
    return f"{ADMIN_DIR}/" if is_admin(meta) else f"{slug(meta['restaurant'])}/"


def store_path(directory):
    """A store's path under the store root, such as app/docs. Handoff ids and relay ids start with it."""
    return f"{directory.parent.name}/{directory.name}"


# Resolved directories of the exclusive locks this process holds.
# A read of one of these takes no second lock. A read of any other store raises.
HELD_LOCKS = []


class Restaurant:
    def __init__(self, directory, owner=None):
        self.dir = Path(directory)
        if not (self.dir / "restaurant.json").is_file():
            raise BrigadeError(f"{self.dir} is not a restaurant (no restaurant.json); run brigade.py open")
        if owner is not None and not re.fullmatch(r".*@\d+", owner):
            raise BrigadeError(f"--owner takes <thread>@<generation>, got {owner!r}")
        self.owner = owner
        # set --thread changes the owner, so it alone writes without matching the recorded one.
        self.unfenced = False
        self._lock_fd = None
        self._lock_depth = 0

    def fence(self):
        """Refuse a write from any thread but the recorded owner. Call it under the lock and keep the lock through the write."""
        meta = self.meta
        if meta.get("generation") is None:
            return
        recorded = f"{meta.get('thread') or ''}@{meta['generation']}"
        if self.owner is None:
            raise BrigadeError(f"this store is owned by {recorded}; pass --owner <thread>@<generation> from status")
        if self.owner != recorded:
            raise BrigadeError(f"owner {self.owner} is stale; this store is owned by {recorded}")
        if not meta.get("thread"):
            raise BrigadeError("this store has no recorded thread; it was retired, and only set --thread --expect restarts it")

    def land_owner(self):
        """The --owner words for land.py: this store's holder prefix at the caller's generation."""
        if self.owner is None:
            return []
        return ["--owner", f"{holder_prefix(self.meta)}@{self.owner.rpartition('@')[2]}"]

    @contextmanager
    def locked(self):
        """Every write in this store holds an exclusive lock on restaurant.lock.

        The lock is on a sidecar file because rewrites replace a table's inode.
        It is reentrant within one Restaurant, so a command can hold it around
        its reads and writes while each write also takes it.
        """
        if self._lock_depth == 0:
            fd = os.open(self.dir / "restaurant.lock", os.O_RDWR | os.O_CREAT, 0o644)
            fcntl.flock(fd, fcntl.LOCK_EX)
            self._lock_fd = fd
            self._held = self.dir.resolve()
            HELD_LOCKS.append(self._held)
        self._lock_depth += 1
        try:
            yield
        finally:
            self._lock_depth -= 1
            if self._lock_depth == 0:
                HELD_LOCKS.remove(self._held)
                os.close(self._lock_fd)
                self._lock_fd = None

    @contextmanager
    def read_lock(self):
        """A shared lock for a read, unless this process already holds this store's lock.

        Under its own lock a command reads its own tables and takes no second lock.
        Reading another store while holding a lock raises, so the caller reads that store first.
        No process holds two stores' locks.
        """
        if self.dir.resolve() in HELD_LOCKS:
            yield
            return
        if HELD_LOCKS:
            raise BrigadeError(
                f"cannot read {self.dir} while holding {HELD_LOCKS[0]}'s lock; "
                "read other stores before taking a lock")
        fd = os.open(self.dir / "restaurant.lock", os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_SH)
            yield
        finally:
            os.close(fd)

    def snapshot(self, table, offset=0):
        """The bytes of a table from offset to its end, copied while no writer can repair a tail or append.

        Every table read goes through here, rows and sync included. None when the table does not exist.
        """
        with self.read_lock():
            try:
                fd = os.open(self.dir / table, os.O_RDONLY)
            except FileNotFoundError:
                return None
            try:
                os.lseek(fd, offset, os.SEEK_SET)
                chunks = []
                while chunk := read_chunk(fd):
                    chunks.append(chunk)
            finally:
                os.close(fd)
        return b"".join(chunks)

    @contextmanager
    def checked(self):
        """One command's checks and writes, run against tables that all parse.

        Nothing inside may wait on stdin, a subprocess, or a sleep. That would stop every other command on this store.
        """
        with self.locked():
            for table in TABLES:
                self.rows(table)
            yield

    @contextmanager
    def guarded(self):
        """The one gate for every change this command makes: the store lock, then the owner fence, held through the change."""
        with self.locked():
            if not self.unfenced:
                self.fence()
            yield

    def write(self, relative, text):
        self.publish(self.dir / relative, text)

    def publish(self, path, text):
        """Write a file this store owns, or a handoff into a sibling's inbox."""
        with self.guarded():
            write_atomic(path, text)

    def remove(self, path):
        with self.guarded():
            path.unlink()

    @property
    def meta(self):
        return json.loads((self.dir / "restaurant.json").read_text())

    def change_meta(self, drop=(), **fields):
        """Reread restaurant.json under the lock and change only these fields.

        A command that read the file before a replacement can then never write the old owner back.
        """
        with self.guarded():
            meta = self.meta
            meta.update(fields)
            for key in drop:
                meta.pop(key, None)
            self.write("restaurant.json", json.dumps(meta, indent=2) + "\n")
            return meta

    def rows(self, table):
        data = self.snapshot(table)
        if data is None:
            return []
        try:
            text = data.decode()
        except UnicodeDecodeError as error:
            number = data[:error.start].count(b"\n") + 1
            raise BrigadeError(f"{table} line {number} is malformed; fix or remove it") from error
        rows = []
        # The last element is the text after the final newline: empty, or the tail of a killed append.
        for number, line in enumerate(text.split("\n")[1:-1], start=2):
            row = parse_row(table, line)
            if row is None:
                raise BrigadeError(f"{table} line {number} is malformed; fix or remove it")
            rows.append(row)
        return rows

    def save_rows(self, table, rows):
        header = TABLES[table]
        body = ["\t".join(header)] + ["\t".join(clean(row.get(key, "")) for key in header) for row in rows]
        self.write(table, "\n".join(body) + "\n")

    def append(self, table, row):
        data = ("\t".join(clean(row.get(key, "")) for key in TABLES[table]) + "\n").encode()
        path = self.dir / table
        with self.guarded():
            if not path.exists():
                self.save_rows(table, [])
            fd = os.open(path, os.O_RDWR | os.O_APPEND)
            try:
                end = os.fstat(fd).st_size
                if end and os.pread(fd, 1, end - 1) != b"\n":
                    # A killed append left an unfinished tail. Writing after it would join two rows.
                    end = os.pread(fd, end, 0).rfind(b"\n") + 1
                    os.ftruncate(fd, end)
                written = os.write(fd, data)
                if written != len(data):
                    os.ftruncate(fd, end)
                    raise BrigadeError(f"wrote {written} of {len(data)} bytes to {table}; nothing appended")
            finally:
                os.close(fd)

    def log(self, kind, ident, state, note=""):
        with self.guarded():
            self.append("log.tsv", {"at": now(), "kind": kind, "id": ident, "state": state, "note": note})
            self.change_meta(lastActivityAt=now())

    def next_id(self, table):
        numbers = [int(row["id"][1:]) for row in self.rows(table) if row.get("id", "")[1:].isdigit()]
        return f"{PREFIX[table]}{max(numbers, default=0) + 1}"

    def find(self, table, ident):
        rows = self.rows(table)
        for row in rows:
            if row["id"] == ident:
                return rows, row
        raise BrigadeError(f"no {ident} in {table}")

    def update(self, table, ident, kind, note=None, **fields):
        rows, row = self.find(table, ident)
        changed = {key: value for key, value in fields.items() if value is not None}
        moved = "state" in changed and changed["state"] != row.get("state")
        row.update(changed)
        self.save_rows(table, rows)
        if moved:
            self.log(kind, ident, changed["state"], note or row.get("summary") or row.get("question", ""))
        return row


REPORTING = ("every-turn", "milestones", "digest")
CLAIM_WAIT_SECONDS = 1.0
PURPOSE_TEMPLATE = "What this restaurant exists to achieve"
OFF_MENU_TEMPLATE = "Work this restaurant does not take"


def reporting_of(meta):
    value = meta.get("reporting")
    if value in (None, ""):
        return "milestones"
    return value


def menu_section(text, heading):
    match = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    return match.group(1).strip() if match else ""


def siblings(directory, project_root):
    """The other coordinators in this project directory on the same project root, by directory name."""
    found = {}
    for meta_path in sorted(directory.parent.glob("*/restaurant.json")):
        if meta_path.parent == directory:
            continue
        try:
            meta = json.loads(meta_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if meta.get("projectRoot") == project_root:
            found[meta_path.parent.name] = meta
    return found


def sibling_lines(restaurant):
    blocks = []
    for directory_name, meta in siblings(restaurant.dir, restaurant.meta.get("projectRoot")).items():
        meta_path = restaurant.dir.parent / directory_name / "restaurant.json"
        menu_path = meta_path.parent / "menu.md"
        menu = menu_path.read_text() if menu_path.is_file() else ""
        purpose = menu_section(menu, "Purpose")
        if not purpose or purpose.startswith(PURPOSE_TEMPLATE):
            purpose = "not written yet"
        else:
            purpose = " ".join(purpose.split())
        off = menu_section(menu, "Off the menu")
        if not off or off.startswith(OFF_MENU_TEMPLATE):
            off_line = "not written yet"
        else:
            off_line = "; ".join(line.strip() for line in off.splitlines() if line.strip())
        thread = (meta.get("thread") or "").strip() or "not recorded"
        name = meta.get("restaurant") or meta_path.parent.name
        blocks.append(
            f"sibling {name} ({meta_path.parent}), thread {thread}\n"
            f"  purpose: {purpose}\n"
            f"  off the menu: {off_line}")
    return blocks


def _read_meta(path):
    try:
        text = path.read_text()
    except OSError:
        return None, "missing"
    try:
        return json.loads(text), "ok"
    except json.JSONDecodeError:
        return None, "invalid"


def wait_for_meta(directory):
    path = directory / "restaurant.json"
    deadline = time.monotonic() + CLAIM_WAIT_SECONDS
    while True:
        meta, state = _read_meta(path)
        if state == "ok":
            return meta
        if time.monotonic() >= deadline:
            if state == "invalid":
                raise BrigadeError(f"{path} is not valid JSON")
            raise BrigadeError(f"{directory} has no restaurant.json after one second")
        time.sleep(0.01)


def intake_owner(directory, project_root, source):
    for name, meta in siblings(directory, project_root).items():
        if source in (meta.get("intake") or []):
            return name
    return None


def refuse_owned_intake(directory, project_root, sources):
    for source in sources:
        owner = intake_owner(directory, project_root, source)
        if owner:
            raise BrigadeError(f"{owner} already owns intake from {source}; move tickets to it instead")


def intake_list(text):
    sources = []
    for item in text.split(","):
        item = clean(item)
        if item and item not in sources:
            sources.append(item)
    return sources


def base_source(source):
    """A taken ticket's source is `<source> (from <handoff id>)`, and a request's ticket `<source> (request A<n>)`.

    The intake source is the part before.
    """
    return re.split(r" \((?:from|request) ", source, maxsplit=1)[0]


def set_intake(restaurant, sources):
    meta = restaurant.meta
    refuse_owned_intake(restaurant.dir, meta.get("projectRoot"), sources)
    for source in meta.get("intake") or []:
        if source in sources:
            continue
        held = [row for row in restaurant.rows("rail.tsv")
                if base_source(row["source"]) == source and row["state"] in LIVE_TICKET_STATES]
        if held:
            raise BrigadeError(f"{held[0]['id']} from {source} is {held[0]['state']}; finish, drop, or move it before dropping {source} from intake")
    meta["intake"] = sources
    return meta


def handoff_id(directory, ticket):
    """Unique across the store: the source store's path under the store root, then the ticket."""
    return f"{directory.parent.name}/{directory.name}/{ticket}"


def inbox_file(directory, handoff):
    return directory / "inbox" / f"{handoff.replace('/', '~')}.json"


def sibling_rails(restaurant):
    """Each sibling's rail.tsv, read before this store's lock is taken.

    The caller's lock never held a sibling still, so reading it first is the same check.
    """
    rails = {}
    for name in siblings(restaurant.dir, restaurant.meta.get("projectRoot")):
        directory = (restaurant.dir.parent / name).resolve()
        rails[directory] = Restaurant(directory).rows("rail.tsv")
    return rails


def taken_row(rows, handoff):
    """The ticket filed for this handoff among these rail rows, if any."""
    if not rows:
        return None
    marker = f"(from {handoff})"
    return next((row for row in rows if row["source"].endswith(marker)), None)


def is_live(directory, row, rails):
    """waiting and assigned are live. moved is as live as the ticket it became. A handoff not yet taken is live."""
    if row["state"] != "moved":
        return row["state"] in LIVE_TICKET_STATES
    target = (directory.parent / row["dish"].removeprefix("to:")).resolve()
    if target in rails:
        rows = rails[target]
    elif not (target / "restaurant.json").is_file():
        return True
    else:
        rows = Restaurant(target).rows("rail.tsv")
    taken = taken_row(rows, handoff_id(directory, row["id"]))
    return taken is None or is_live(target, taken, rails)


def refuse_live_ref(restaurant, ref, rails):
    if not ref:
        return
    own = restaurant.dir.resolve()
    own_rows = restaurant.rows("rail.tsv")
    rails = {**rails, own: own_rows}
    stores = [(own, own_rows)]
    stores.extend((directory, rows) for directory, rows in rails.items() if directory != own)
    for directory, rows in stores:
        for row in rows:
            if row["ref"] == ref and is_live(directory, row, rails):
                where = "" if directory == own else f" in {directory.name}"
                raise BrigadeError(f"{ref} is already {row['id']}{where} ({row['state']}); nothing added")


def add_ticket(restaurant, summary, source, ref, request="", rails=None, again=False):
    source, ref, request = clean(source), clean(ref), clean(request)
    meta = restaurant.meta
    if request:
        # A replayed request file must not file a second ticket, whatever state the first reached.
        for row in restaurant.rows("rail.tsv"):
            if row["source"].endswith(f"(request {request})"):
                raise BrigadeError(f"request {request} is already {row['id']}; nothing added")
    if source != "user":
        owner = intake_owner(restaurant.dir, meta.get("projectRoot"), source)
        if owner:
            raise BrigadeError(f"{owner} owns intake from {source}; ask it to file this and move it here")
        if source not in (meta.get("intake") or []):
            raise BrigadeError(f"no coordinator owns intake from {source}; the one that reads it runs set --intake {source}")
    refuse_live_ref(restaurant, ref, rails or {})
    if source == "user" and not ref and not again:
        for row in restaurant.rows("rail.tsv"):
            if row["state"] in LIVE_TICKET_STATES and same_text(row["summary"]) == same_text(summary):
                raise BrigadeError(f"same text as {row['id']} ({row['state']}); nothing added; "
                                   "pass --again to file a second ticket")
    if request:
        source = f"{source} (request {request})"
    return append_ticket(restaurant, summary, source, ref)


def append_ticket(restaurant, summary, source, ref):
    ident = restaurant.next_id("rail.tsv")
    restaurant.append("rail.tsv", {"id": ident, "at": now(), "state": "waiting", "source": source,
                                   "ref": ref, "summary": summary})
    restaurant.log("ticket", ident, "waiting", summary)
    return ident


def item_report(restaurant, report):
    """The bare name of an item report under this store's reports/.

    Its content is read, so the file must be a regular file that resolves to this store's reports/<name>.
    A path that names a file elsewhere is refused instead of re-anchored as review_report does, and so is a symbolic link.
    A `..` component is refused as written, before anything is resolved.
    """
    if ".." in Path(report).parts:
        raise BrigadeError(f"{report} has a .. component; name a file like reports/D2.md")
    name = Path(report).name
    if not ITEM_REPORT.fullmatch(name):
        raise BrigadeError(f"{name} is not an item report; name a file like reports/D2.md")
    path = restaurant.dir / "reports" / name
    home = restaurant.dir.resolve() / "reports" / name
    if report not in (name, f"reports/{name}") and Path(report).parent.resolve() != home.parent:
        raise BrigadeError(f"{report} is outside this store's reports/; name reports/{name}")
    if path.is_symlink():
        raise BrigadeError(f"reports/{name} is a symbolic link; nothing added")
    if not path.is_file():
        raise BrigadeError(f"reports/{name} does not exist; nothing added")
    if path.resolve() != home:
        raise BrigadeError(f"reports/{name} resolves outside this store's reports/; nothing added")
    return name


@dataclass(frozen=True)
class FollowUps:
    """What a report's follow-ups sections hold. A report with no such section is None, not this.

    Each of `items` becomes one ticket, and its position plus one is the `#<n>` in its ref.
    `asides` are the (reason, text) pairs the command prints and never files.
    """
    items: tuple
    asides: tuple


# A block that is one of these and nothing more says the report has no follow-up. Every longer block is read as work.
NO_WORK = ("none", "none required", "none needed", "nothing", "nothing needed", "n/a", "not applicable", "no follow-ups")


def says_no_work(text):
    """True when the block is one of NO_WORK and nothing more.

    Case does not count. Neither do list markers, the `*`, `_`, and backtick marks around it, or a final period.
    """
    text = re.sub(r"^(?:(?:[-*+]|\d+[.)])\s+)+", "", text.strip())
    return text.strip("*_` ").removesuffix(".").strip("*_` ").casefold() in NO_WORK


def follow_ups(text):
    """Every follow-ups section of a report, or None when no heading says follow-ups.

    A top-level list item or a paragraph is one block, and the indented lines, nested bullets, and fenced code under it
    are part of it. Each block is a follow-up, with three exceptions that are asides. A block that is one of NO_WORK
    and nothing more is one. So is a paragraph directly above a list item, which introduces the list, and a paragraph
    below its section's last list item, which closes the section.
    """
    sections, level, fenced, blank, block = [], 0, False, True, None
    for line in text.splitlines():
        fence = line.strip().startswith("```")
        plain = not fence and not fenced
        fenced = fenced != fence
        heading = plain and re.match(r"(#{1,6})(\s|$)", line)
        if heading:
            depth = len(heading.group(1))
            if re.match(r"#{1,6}\s+follow-?ups?\b", line, re.I):
                level = depth
                sections.append([])
            elif depth <= level:
                level = 0
            block, blank = None, True
        elif not level:
            continue
        elif not line.strip():
            blank = plain
        else:
            marker = plain and re.match(r"(?:[-*+]|\d+[.)])\s+", line)
            if marker or block is None or plain and blank and not line[0].isspace():
                block = ("item" if marker else "para", [])
                sections[-1].append(block)
            block[1].append(line[marker.end():] if marker else line)
            blank = False
    if not sections:
        return None
    items, asides = [], []
    for blocks in sections:
        blocks = [(kind, " ".join(part.strip() for part in lines).strip()) for kind, lines in blocks]
        blocks = [(kind, text) for kind, text in blocks if text]
        kinds = [kind for kind, _ in blocks] + ["end"]
        last = max((index for index, kind in enumerate(kinds) if kind == "item"), default=len(kinds))
        for index, (kind, text) in enumerate(blocks):
            if says_no_work(text):
                asides.append(("says no work is needed", text))
            elif kind == "para" and kinds[index + 1] == "item":
                asides.append(("prose that introduces a list", text))
            elif kind == "para" and index > last:
                asides.append(("prose after the last list item", text))
            else:
                items.append(text)
    return FollowUps(tuple(items), tuple(asides))


def same_text(value):
    return " ".join(value.split()).casefold()


def file_follow_ups(restaurant, name, found, write):
    """One waiting ticket per follow-up whose text no ticket of this store holds, in any state.

    A done or dropped ticket counts, so a rerun on the same report after the coordinator dropped one files nothing.
    The ref ends in a position, which is not an identity, so the text is the only key and refuse_live_ref is not asked.
    """
    restaurant.find("dishes.tsv", name[:-3])
    if found is None:
        return f"reports/{name} has no follow-ups section; nothing added"
    aside = [f"not filed, {reason}: {text}" for reason, text in found.asides]
    if not found.items:
        return "\n".join([f"reports/{name} lists no follow-ups; nothing added", *aside])
    holders = {}
    for row in sorted(restaurant.rows("rail.tsv"), key=lambda row: row["state"] not in LIVE_TICKET_STATES):
        holders.setdefault(same_text(row["summary"]), f"{row['id']} ({row['state']})")
    lines = []
    for number, text in enumerate(found.items, 1):
        ref = f"{restaurant.dir.name}/reports/{name}#{number}"
        key = same_text(text)
        if key in holders:
            lines.append(f"skipped {ref}, same text as {holders[key]}: {text}")
        elif write:
            ident = append_ticket(restaurant, text, "report", ref)
            holders[key] = f"{ident} (waiting)"
            lines.append(f"{ident} added from {ref}: {text}")
        else:
            holders[key] = f"#{number} above"
            lines.append(f"would add from {ref}: {text}")
    return "\n".join(lines + aside)


def sibling_named(restaurant, to):
    """A sibling's directory name and restaurant.json, found by directory name or restaurant name."""
    meta = restaurant.meta
    names = siblings(restaurant.dir, meta.get("projectRoot"))
    name = to if to in names else next((n for n in names if slug(names[n].get("restaurant") or n) == slug(to)), None)
    if name is None:
        raise BrigadeError(f"{to} is not a sibling coordinator on {meta.get('projectRoot')}")
    return name, names[name]


def tell(name, meta):
    thread = (meta.get("thread") or "").strip()
    return f"tell thread {thread}" if thread else f"no thread recorded for {name}"


def move_ticket(restaurant, ident, to, rails):
    name, sibling = sibling_named(restaurant, to)
    target = (restaurant.dir.parent / name).resolve()
    destination = f"to:{name}"
    rows, row = restaurant.find("rail.tsv", ident)
    if row["state"] == "moved" and row["dish"] != destination:
        raise BrigadeError(f"{ident} is already moved to {row['dish'].removeprefix('to:')}")
    if row["state"] not in ("waiting", "moved"):
        raise BrigadeError(f"{ident} is {row['state']}; only a waiting ticket moves")
    if row["state"] == "waiting":
        # State and destination commit in one rewrite, so the ref stays live here from this point on.
        row["state"], row["dish"] = "moved", destination
        restaurant.save_rows("rail.tsv", rows)
    if not any(event["kind"] == "ticket" and event["id"] == ident and event["state"] == "moved"
               for event in restaurant.rows("log.tsv")):
        restaurant.log("ticket", ident, "moved", f"{row['summary']} (to {name})")
    handoff = handoff_id(restaurant.dir, ident)
    target_rows = rails.get(target)
    if target_rows is None:
        target_rows = Restaurant(target).rows("rail.tsv")
    if taken_row(target_rows, handoff) is None:
        restaurant.publish(inbox_file(target, handoff), json.dumps({
            "handoff": handoff, "summary": row["summary"], "source": base_source(row["source"]), "ref": row["ref"],
        }, indent=2) + "\n")
    return f"{ident} moved to {name}; {tell(name, sibling)}"


def take_tickets(restaurant):
    lines = []
    for path in sorted((restaurant.dir / "inbox").glob("*.json")):
        try:
            handoff = json.loads(path.read_text())
        except json.JSONDecodeError as error:
            raise BrigadeError(f"{path} is not valid JSON: {error}") from error
        source = handoff["handoff"]
        row = taken_row(restaurant.rows("rail.tsv"), source)
        if row is None:
            rows = restaurant.rows("rail.tsv")
            row = {"id": restaurant.next_id("rail.tsv"), "at": now(), "state": "waiting",
                   "source": f"{handoff['source']} (from {source})", "ref": handoff["ref"], "summary": handoff["summary"]}
            restaurant.save_rows("rail.tsv", rows + [row])
        if not any(event["kind"] == "ticket" and event["note"] == f"from {source}" for event in restaurant.rows("log.tsv")):
            restaurant.log("ticket", row["id"], "waiting", f"from {source}")
        restaurant.remove(path)
        lines.append(f"{row['id']} from {source}: {row['summary']}")
    return lines


def request_files(restaurant):
    """Request files the executive admin published into this inbox, oldest first, as (pending, finished).

    A file whose id has an inbox-done row is finished. request --republish reads completions before
    the admin's lock, so it can publish a request inbox done finished meanwhile. Nothing counts that file.
    """
    found = sorted((path for path in (restaurant.dir / "inbox").glob("A*.line") if re.fullmatch(r"A\d+", path.stem)),
                   key=lambda path: int(path.stem[1:]))
    finished = finished_requests(restaurant)
    return [path for path in found if path.stem not in finished], [path for path in found if path.stem in finished]


def finished_requests(restaurant):
    return {row["id"] for row in restaurant.rows("log.tsv") if row["kind"] == "inbox-done"}


def take_inbox(restaurant):
    """File handed tickets, then print each request waiting for inbox done. A finished request's file is deleted."""
    lines = take_tickets(restaurant)
    pending, finished = request_files(restaurant)
    for path in finished:
        restaurant.remove(path)
    lines.extend(f"{path.stem}: {path.read_text().strip()}" for path in pending)
    return "\n".join(lines) or NOTHING_HANDED


def finish_request(restaurant, ident):
    """Record the request as acted on, then delete its file. A rerun after a crash between the two finishes the delete."""
    path = restaurant.dir / "inbox" / f"{ident}.line"
    if ident not in finished_requests(restaurant):
        if not path.exists():
            raise BrigadeError(f"no request {ident} in the inbox")
        restaurant.log("inbox-done", ident, "done", path.read_text().strip())
    if path.exists():
        restaurant.remove(path)
    return f"{ident} done"


def handed_count(restaurant):
    return len(list((restaurant.dir / "inbox").glob("*.json")))


def open_restaurant(root, project_root, name, reporting="milestones", intake=(), workers=None, admin=False, mode=None):
    project_root = Path(project_root).resolve()
    if admin:
        name = ADMIN_NAME
    directory = root / slug(project_root.name) / (ADMIN_DIR if admin else slug(name))
    # The project directory is shared by every coordinator on this path slug.
    # The coordinator directory is the claim, so mkdir must fail when it exists.
    directory.parent.mkdir(parents=True, exist_ok=True)
    try:
        directory.mkdir()
    except FileExistsError:
        created = False
    else:
        created = True
    if not created:
        meta = wait_for_meta(directory)
        if meta.get("projectRoot") != str(project_root):
            other = meta.get("projectRoot")
            raise BrigadeError(f"{directory} already holds a coordinator for {other}; pick another --name")
        return Restaurant(directory), False
    try:
        refuse_owned_intake(directory, str(project_root), intake)
    except BrigadeError:
        directory.rmdir()
        raise
    for filename, template in (("menu.md", ADMIN_MENU if admin else MENU), ("house-rules.md", HOUSE_RULES)):
        write_atomic(directory / filename, template.format(restaurant=name))
    for table in TABLES:
        if table == "rulings.tsv" and not admin:
            continue
        header = TABLES[table]
        write_atomic(directory / table, "\t".join(header) + "\n")
    meta = {"restaurant": name, "projectRoot": str(project_root),
            "reporting": reporting, "openedAt": now(), "lastActivityAt": now(),
            "lastReportAt": None, "thread": None, "schedules": {}, "intake": list(intake)}
    if workers is not None:
        meta["workers"] = workers
    if mode is not None:
        meta["mode"] = mode
    if admin:
        meta["role"] = "admin"
    write_atomic(directory / "restaurant.json", json.dumps(meta, indent=2) + "\n")
    return Restaurant(directory), True


def counts(restaurant):
    tickets = [row["state"] for row in restaurant.rows("rail.tsv")]
    dishes = [row["state"] for row in restaurant.rows("dishes.tsv")]
    questions = [row for row in restaurant.rows("86.tsv") if row["state"] == "open"]
    return {
        "waiting tickets": tickets.count("waiting"),
        "in progress": dishes.count("in-progress"),
        "in review": dishes.count("in-review"),
        "passed review": dishes.count("passed"),
        "waiting to land": dishes.count("queued"),
        "sent back": dishes.count("sent-back"),
        "blocked": dishes.count("blocked"),
        "merged": dishes.count("merged"),
        "decisions for you": len(questions),
        "handed to you": handed_count(restaurant),
        "requests from the user": len(request_files(restaurant)[0]),
    }


def status_line(restaurant):
    return ", ".join(f"{label}: {value}" for label, value in counts(restaurant).items() if value) or "nothing on record"


@functools.cache
def roles_family():
    """roles.py's family, loaded in process.

    pass record asks under the store lock, which forbids a subprocess.
    runpy writes no __pycache__ under skills/.
    """
    return runpy.run_path(str(roles_script()))["family"]


def cross_family(row):
    family = roles_family()
    return family(row["author"]) != family(row["verifier"]) and not row["note"].startswith("same model family")


def item_verdicts(rows, dish_id):
    """The rows that carry the item's verdict. A panel member's row is on record and decides nothing."""
    return [row for row in rows if row["dish"] == dish_id and not row["member"]]


def send_backs(rows, dish_id):
    return [row for row in item_verdicts(rows, dish_id) if row["verdict"] == "send-back"]


def round_count(restaurant, dish_id):
    """The item's send-backs written after the later of its last passing verdict and its last answered round decision.

    Only a row `86 add --round-budget` wrote is a round decision. Another decision's answer never settles the count.
    """
    verdicts = item_verdicts(restaurant.rows("pass.tsv"), dish_id)
    settled = [row["at"] for row in verdicts if row["verdict"] == "pass"]
    settled += [row["answered"] for row in restaurant.rows("86.tsv")
                if row["dish"] == dish_id and row["kind"] == ROUND_KIND and row["state"] == "answered"]
    since = max(settled, default="")
    return sum(row["verdict"] == "send-back" and row["at"] > since for row in verdicts)


def round_debt(restaurant, dish):
    """The item's round count when it owes its round decision, else 0.

    The budget stops another fix round, so only an item that could get one owes.
    """
    if dish["state"] not in OWING_STATES:
        return 0
    count = round_count(restaurant, dish["id"])
    return count if count >= ROUND_BUDGET else 0


def fix_round_refusal(restaurant, dish):
    """Why the item gets no fix round now, or None."""
    debt = round_debt(restaurant, dish)
    if not debt:
        return None
    return (f"{dish['id']} has {debt} send-backs; no fix round until its decision is answered; "
            f"run 86 add --dish {dish['id']} --round-budget")


def round_decision(restaurant, dish_id):
    """The question, options, and default of the decision an item owes at ROUND_BUDGET send-backs."""
    _, dish = restaurant.find("dishes.tsv", dish_id)
    if dish["state"] not in OWING_STATES:
        raise BrigadeError(f"{dish_id} is {dish['state']}; it owes no round decision")
    count = round_count(restaurant, dish_id)
    if count < ROUND_BUDGET:
        raise BrigadeError(f"{dish_id} has {count} send-back{'' if count == 1 else 's'} since its last pass or round decision; "
                           f"the decision opens at {ROUND_BUDGET}")
    question = (f"{dish_id} was sent back {count} times. Accept the remaining findings as known limits and land it, "
                "send it through architect for a redesign, or drop it?")
    report = send_backs(restaurant.rows("pass.tsv"), dish_id)[-1]["report"]
    if report:
        question += f" Findings: reports/{report}."
    return question, ", ".join((*ROUND_DECISIONS, ROUND_PARKED)), ROUND_PARKED


def latest_verdict(restaurant, dish_id, sha):
    restaurant.find("dishes.tsv", dish_id)
    verdicts = [row for row in item_verdicts(restaurant.rows("pass.tsv"), dish_id) if row["sha"] == sha]
    return verdicts[-1] if verdicts else None


def pass_json(row):
    return json.dumps({"verdict": row["verdict"], "author": row["author"], "verifier": row["verifier"],
                       "note": row["note"], "crossFamily": cross_family(row)}, indent=2)


def pass_check(restaurant, dish_id, sha):
    latest = latest_verdict(restaurant, dish_id, sha)
    if latest is None:
        return False, f"{dish_id} has no review verdict for {sha}"
    if latest["verdict"] != "pass":
        return False, f"{dish_id} at {sha}: {latest['verdict']} ({latest['note'] or 'no note'})"
    return True, f"{dish_id} at {sha} passed review by {latest['verifier']}"


def review_report(restaurant, dish_id, report):
    name = Path(report).name
    match = REVIEW_FILE.fullmatch(name)
    if not match or match.group(1) != dish_id:
        raise BrigadeError(f"{name} is not a review report of {dish_id}; name a file like reports/{dish_id}-review-1.md")
    if not (restaurant.dir / "reports" / name).exists():
        raise BrigadeError(f"reports/{name} does not exist; write the review report first")
    return name


def record_pass(restaurant, dish_id, pr, sha, verdict, author, verifier, note="", same_family=False, report="",
                member=False, late=False):
    _, dish = restaurant.find("dishes.tsv", dish_id)
    if verdict not in VERDICTS:
        raise BrigadeError(f"verdict must be one of {', '.join(VERDICTS)}")
    if roles_family()(author) == roles_family()(verifier) and not same_family:
        raise BrigadeError(f"verifier {verifier} is the same model family as author {author}; "
                           "pick a verifier from another family, or pass --same-family when no other family is runnable")
    if same_family:
        note = clean(f"same model family; {note}")
    if report:
        report = review_report(restaurant, dish_id, report)
    restaurant.append("pass.tsv", {"at": now(), "dish": dish_id, "pr": pr, "sha": sha, "verdict": verdict,
                                   "author": author, "verifier": verifier, "note": note, "report": report,
                                   "member": "yes" if member else ""})
    if member:
        return f"{dish_id}: member {verdict} on record; {dish_id} stays {dish['state']}"
    if late:
        printed = f"{dish_id}: late {verdict} on record; {dish_id} stays {dish['state']}"
    else:
        dish = restaurant.update("dishes.tsv", dish_id, "dish", state=VERDICTS[verdict], pr=pr, sha=sha)
        printed = f"{dish_id} {dish['state']}"
    debt = round_debt(restaurant, dish) if verdict == "send-back" else 0
    if debt:
        return f"{printed}; {debt} send-backs, decision pending"
    return printed


def unrecorded_reviews(restaurant):
    """The review reports under reports/ that no pass.tsv row accounts for, by file name.

    A row that names no report cannot say which file it reviewed, so it accounts for every report of its dish written before it.
    """
    rows = restaurant.rows("pass.tsv")
    reports = restaurant.dir / "reports"
    missing = []
    for path in sorted(reports.iterdir()) if reports.is_dir() else []:
        match = REVIEW_FILE.fullmatch(path.name)
        if not match:
            continue
        written = path.stat().st_mtime
        if not any(row["report"] == path.name if row["report"]
                   else datetime.fromisoformat(row["at"].replace("Z", "+00:00")).timestamp() >= written
                   for row in rows if row["dish"] == match.group(1)):
            missing.append(path.name)
    return missing


def report(restaurant, write=True):
    meta = restaurant.meta
    since = meta.get("lastReportAt") or ""
    latest = {}
    for event in restaurant.rows("log.tsv"):
        if event["at"] > since:
            latest[(event["kind"], event["id"])] = event
    sections = {title: [] for title in SECTIONS.values()}
    for (kind, _), event in latest.items():
        title = SECTIONS.get((kind, event["state"]))
        if title:
            sections[title].append(event)
    dishes = {row["id"]: row for row in restaurant.rows("dishes.tsv")}
    stamp = now()
    lines = [f"# {meta['restaurant']} report", "", f"Since {since or 'opening'}. {status_line(restaurant)}.", ""]
    for title, items in sections.items():
        if not items:
            continue
        lines += [f"## {title}", ""]
        for event in items:
            dish = dishes.get(event["id"], {}) if event["kind"] in ("dish", "mode") else {}
            tickets = f" ({dish['tickets'].replace(',', ', ')})" if dish.get("tickets") else ""
            pr = f" {dish['pr']}" if dish.get("pr") else ""
            lines.append(f"- {event['id']}{tickets}: {event['note']}{pr}")
        lines.append("")
    if is_admin(meta):
        lines += admin_sections(restaurant, since)
    questions = [row for row in restaurant.rows("86.tsv") if row["state"] == "open"]
    if questions:
        lines += ["## Decisions for you", ""]
        lines += [f"- {q['id']}: {q['question']} Options: {q['options']}. Default if no answer: {q['default']}." for q in questions]
        lines.append("")
    if len(lines) == 4:
        lines += ["Nothing new.", ""]
    text = "\n".join(lines)
    path = None
    if write:
        path = restaurant.dir / "closeouts" / f"{stamp[:26].replace(':', '')}.md"
        restaurant.write(path.relative_to(restaurant.dir), text)
        restaurant.change_meta(lastReportAt=stamp)
    return text, path


MEASURING_STATIONS = ("perf-issue", "hillclimb", "eval")
LAND = Path(__file__).resolve().parents[2] / "landing" / "scripts" / "land.py"
BUILT_ROLES = Path(__file__).resolve().parents[2] / "pstack-runtime" / "scripts" / "roles.py"
SOURCE_ROLES = Path(__file__).resolve().parents[3] / "scripts" / "roles.py"
ESCALATED = "escalated: "
ATTEMPT_AFTER = {"sent-back": "fix", "queued": "bounce"}
MODE_RESOLUTIONS = 3
SEAT_RULE = ("Seat rule. Copy the Mode value above into --brief-mode on every roles.py mode and roles.py show call you make, "
             "and pass no other mode flag. Never pass --session-mode. Mode source names where your launcher's decision came "
             "from. It does not make this thread a session.")
WAIT_RULE = ("- Never end your turn while a child task you started with delegate_task is still open, per step 5 of the "
             "pstack-runtime skill's Delegation section. This overrides delegate_task's text that says to end the turn and "
             "wait for a notification. A completion wakes you only when the child's run ends, and a stalled child or a run "
             "left open never ends. Wait on each open child task with t3_thread_wait on its childThreadId and timeoutMs "
             "300000, then read it with task_status. A child whose run is still open and whose last message holds the result "
             "is stalled after two minutes with no new activity, per step 5. If that wait returns at once while workState is "
             "still working or waiting_for_children, the child's run ended with its task open. Then wait between task_status "
             "checks with t3_thread_wait and timeoutMs 120000 on your own thread, the parentThreadId from "
             "orchestrator_capabilities, with runId set to its activeRunId from t3_thread_read, never a shell sleep, and "
             "count ten minutes from its last activity item. "
             "A child task is open while its workState is working or "
             "waiting_for_children, whatever hasPendingChildRuns says. Cancel a child task with task_cancel when it runs past "
             "its budget or stalls, per the runtime's Failure handling. A thread you launched with t3_thread_launch has no "
             "parent, so its finished turn never wakes you. While it stays healthy, repeat t3_thread_wait on its threadId with "
             "timeoutMs 300000 and read its activity with t3_thread_read. A timeout alone never stops it. Stop it with "
             "t3_thread_interrupt and then a terminal t3_thread_wait only when it stalls, with no new activity item for ten "
             "minutes per step 5 of the runtime's Delegation section, or runs past its budget. A long-lived "
             "owner your playbook supervises, such as an Orchestrate PR owner, follows the runtime's Top-level threads section "
             "and its playbook instead, and does not hold your report. Write the report only once every child task and every "
             "other thread you launched is terminal.")


def holder(restaurant, dish):
    return f"{slug(restaurant.meta['restaurant'])}/{dish}"


class ClaimError(BrigadeError):
    """land.py refused a lease claim. fire records the block and adds its own prefix."""


def worker_cap(meta):
    value = meta.get("workers")
    if value in (None, ""):
        return 2
    return int(value)


def require_workers(workers):
    if workers is not None and workers < 1:
        raise BrigadeError("workers must be 1 or more")


def running_workers(restaurant):
    return sum(row["state"] in COUNTED_STATES for row in restaurant.rows("dishes.tsv"))


def workers_full(restaurant):
    cap = worker_cap(restaurant.meta)
    running = running_workers(restaurant)
    if running >= cap:
        return f"{running} of {cap} workers running"
    return None


def changelog_fragment(branch):
    encoded = branch.replace("%", "%25").replace("/", "%2F")
    return f"changes/{encoded}.md"


def with_fragment(paths, branch):
    if not paths or not branch:
        return paths
    fragment = changelog_fragment(branch)
    parts = [part for part in paths.split(",") if part]
    if fragment not in parts:
        parts.append(fragment)
    return ",".join(parts)


def refusal_kind(message):
    if "repository at its cap" in message:
        return "repository"
    return "lease"


def block_note(kind, ids, station, summary, paths, timebox, branch="", reason=""):
    note = {"kind": kind, "tickets": list(ids), "station": station, "summary": summary,
            "paths": paths, "timebox": timebox}
    if branch:
        note["branch"] = branch
    if reason:
        note["reason"] = reason
    return json.dumps(note, separators=(",", ":"))


def record_blocked(restaurant, ids, kind, station, summary, paths, timebox, branch="", reason=""):
    waiting = {row["id"] for row in restaurant.rows("rail.tsv") if row["state"] == "waiting"}
    note = block_note(kind, ids, station, summary, paths, timebox, branch, reason)
    for ident in ids:
        if ident in waiting:
            restaurant.log("ticket", ident, "blocked", note)


def blocked_waiting(restaurant):
    latest = {}
    for event in restaurant.rows("log.tsv"):
        if event["kind"] == "ticket":
            latest[event["id"]] = event
    found = []
    for ticket in restaurant.rows("rail.tsv"):
        event = latest.get(ticket["id"])
        if ticket["state"] != "waiting" or not event or event["state"] != "blocked":
            continue
        try:
            note = json.loads(event["note"])
        except json.JSONDecodeError:
            continue
        if isinstance(note, dict):
            found.append((ticket["id"], note))
    return found


def land_result(project_root, *args):
    return subprocess.run([sys.executable, str(LAND), "--repo", str(project_root), *args],
                          capture_output=True, text=True)


def contract_mode(project_root):
    """`lands by merge`, or `no landing contract` when land.py status fails."""
    result = land_result(project_root, "status")
    if result.returncode != 0 or not result.stdout.strip():
        return "no landing contract"
    return f"lands by {result.stdout.split(None, 1)[0]}"


def repository_cap(project_root):
    result = land_result(project_root, "status")
    if result.returncode != 0:
        return None
    match = re.search(r"changes in flight: \d+ of (\d+)", result.stdout)
    return int(match.group(1)) if match else None


def claim_lease(restaurant, dish, paths):
    """Claim the dish's paths in the repository's landing queue. A refused claim fires nothing."""
    result = land_result(restaurant.meta["projectRoot"], "lease", "claim",
                         "--holder", holder(restaurant, dish), "--paths", paths, *restaurant.land_owner())
    if result.returncode != 0:
        raise ClaimError(result.stderr.strip().removeprefix("land: "))
    return result.stdout.strip()


def release_lease(restaurant, lease):
    result = land_result(restaurant.meta["projectRoot"], "lease", "release", lease, *restaurant.land_owner())
    if result.returncode != 0:
        diagnostic = (result.stderr or result.stdout).strip().removeprefix("land: ")
        print(f"brigade: warning: could not release {lease}: {diagnostic}", file=sys.stderr)


def lease_check(project_root, holder_name, paths):
    result = land_result(project_root, "lease", "check", "--holder", holder_name, "--paths", paths)
    diagnostic = result.stderr.strip().removeprefix("land: ")
    return result.returncode, result.stdout.strip(), diagnostic


def fire_command(ident, note):
    """Shell-quoted fire line. Each option is one --name=value word so a value that starts with - stays the value."""
    tickets = ",".join(note.get("tickets") or [ident])
    pairs = [
        ("tickets", tickets),
        ("station", note.get("station", "")),
        ("summary", note.get("summary", "")),
    ]
    if note.get("branch"):
        pairs.append(("branch", note["branch"]))
    if note.get("paths"):
        pairs.append(("paths", note["paths"]))
    pairs.append(("timebox", note.get("timebox", 60)))
    if note.get("reason"):
        pairs += [("mode", "full"), ("reason", note["reason"])]
    words = ["fire", *(f"--{name}={value}" for name, value in pairs)]
    return " ".join(shlex.quote(str(word)) for word in words)


def block_holds(project_root, prefix, ident, note, running, cap, next_dish):
    """The block on a waiting ticket that holds now, as (kind, text), or None. Workers come first, as in fire."""
    if running >= cap:
        return "workers", f"waiting for a worker ({running} of {cap} running)"
    requested = note.get("paths") or ""
    if not requested:
        return None
    known = note.get("branch") or f"{prefix}/{next_dish.lower()}"
    code, out, err = lease_check(project_root, f"{prefix}/{ident}", with_fragment(requested, known))
    if code == 0:
        return None
    overlap = re.findall(r"^(L\d+) held by (\S+) on ", out, re.M)
    if overlap:
        return "lease", "waiting on " + ", ".join(f"{lease} ({holder_name})" for lease, holder_name in overlap)
    room = re.search(r"(\d+ of \d+ changes in flight)", out)
    if room:
        return "repository", f"waiting for room in the repository ({room.group(1)})"
    return note.get("kind") or "lease", f"waiting on the landing queue ({out or err or 'lease check failed'})"


def block_inputs(restaurant):
    """What a block recheck reads from the store. Call it under the store lock."""
    return blocked_waiting(restaurant), running_workers(restaurant), worker_cap(restaurant.meta), restaurant.next_id("dishes.tsv")


def recheck_blocks(restaurant, inputs):
    """Each blocked ticket, its note, and the block that holds now or None. land.py runs here, outside the store lock."""
    blocked, running, cap, next_dish = inputs
    root, prefix = restaurant.meta["projectRoot"], slug(restaurant.meta["restaurant"])
    return [(ident, note, block_holds(root, prefix, ident, note, running, cap, next_dish)) for ident, note in blocked]


def holding_blocks(restaurant):
    """The blocks that still hold, by ticket, rechecked as watch does."""
    with restaurant.checked():
        inputs = block_inputs(restaurant)
    return {ident: held for ident, _, held in recheck_blocks(restaurant, inputs) if held}


def ticket_lines(restaurant, state, held):
    lines = []
    for row in restaurant.rows("rail.tsv"):
        if state and row["state"] != state:
            continue
        line = f"{row['id']} {row['state']} [{row['source']}] {row['summary']}"
        if row["ref"]:
            line += f" {row['ref']}"
        if row["state"] == "waiting" and row["id"] in held:
            line += f" blocked: {held[row['id']][0]}"
        lines.append(line)
    return "\n".join(lines)


def unfireable(restaurant, ids):
    # A ticket fired again is the same work, so an item that owes its round decision holds its tickets.
    for dish in restaurant.rows("dishes.tsv"):
        held = [ident for ident in ids if ident in dish["tickets"].split(",")]
        refusal = fix_round_refusal(restaurant, dish) if held else None
        if refusal:
            return f"{held[0]} is {dish['id']}'s ticket; {refusal}"
    for ident in ids:
        _, ticket = restaurant.find("rail.tsv", ident)
        if ticket["state"] != "waiting":
            return f"{ident} is {ticket['state']}, not waiting"
    return None


def fire(restaurant, ids, station, task, thread, branch, summary, timebox, paths, reason=None):
    while True:
        with restaurant.checked():
            restaurant.fence()
            refusal = unfireable(restaurant, ids)
            if refusal:
                raise BrigadeError(refusal)
            dish = restaurant.next_id("dishes.tsv")
            known = branch or f"{slug(restaurant.meta['restaurant'])}/{dish.lower()}"
            leased = with_fragment(paths, known) if paths else ""
            full = workers_full(restaurant)
            if full:
                record_blocked(restaurant, ids, "workers", station, summary, paths, timebox, branch, reason)
                raise BrigadeError(f"nothing fired: {full}")
        # land.py can wait on the landing database, so the claim runs outside the store lock.
        # Another command may fire or take the tickets meanwhile, so the checks run again before the write.
        try:
            lease = claim_lease(restaurant, dish, leased) if leased else ""
        except ClaimError as error:
            with restaurant.checked():
                record_blocked(restaurant, ids, refusal_kind(str(error)), station, summary, paths, timebox, branch, reason)
            raise BrigadeError(f"nothing fired: {error}") from error
        with restaurant.checked():
            refusal = unfireable(restaurant, ids)
            current = restaurant.next_id("dishes.tsv")
            full = None if refusal else workers_full(restaurant)
            if not refusal and not full and current == dish:
                restaurant.append("dishes.tsv", {"id": dish, "at": now(), "state": "in-progress", "station": station,
                                                 "tickets": ",".join(ids), "task": task, "thread": thread,
                                                 "branch": branch, "summary": summary, "timebox": timebox,
                                                 "lease": lease, "paths": leased})
                restaurant.log("dish", dish, "in-progress", summary)
                if reason:
                    record_escalation(restaurant, dish, reason)
                rows = restaurant.rows("rail.tsv")
                for row in rows:
                    if row["id"] in ids:
                        row["state"], row["dish"] = "assigned", dish
                restaurant.save_rows("rail.tsv", rows)
                for row in rows:
                    if row["id"] in ids:
                        restaurant.log("ticket", row["id"], "assigned", row["summary"])
                return f"{dish} (lease {lease} held by {holder(restaurant, dish)})" if lease else dish
            if full and not refusal:
                record_blocked(restaurant, ids, "workers", station, summary, paths, timebox, branch, reason)
                refusal = full
        if lease:
            release_lease(restaurant, lease)
        if refusal:
            raise BrigadeError(f"nothing fired: {refusal}")


def item_escalation(mode, reason):
    if mode is None:
        if reason is not None:
            raise BrigadeError("--reason goes with --mode full")
        return None
    if mode == "light":
        raise BrigadeError("an item's mode only moves to full; change the coordinator with set --mode light")
    if mode != "full":
        raise BrigadeError(f"--mode takes full, got {mode!r}")
    if not clean(reason):
        raise BrigadeError('--mode full needs --reason "<one line>"')
    return clean(reason)


def latest_mode_note(events, ident):
    notes = [event["note"] for event in events if event["kind"] == "mode" and event["id"] == ident]
    return notes[-1] if notes else None


def record_escalation(restaurant, ident, reason):
    restaurant.fence()
    _, dish = restaurant.find("dishes.tsv", ident)
    if dish["state"] not in LEASED_STATES:
        raise BrigadeError(f"{ident} is {dish['state']}; only open work moves to full mode")
    recorded = latest_mode_note(restaurant.rows("log.tsv"), ident)
    if recorded is not None:
        return recorded
    restaurant.log("mode", ident, "full", reason)
    return reason


def menu_purpose(restaurant):
    text = (restaurant.dir / "menu.md").read_text()
    match = re.search(r"^## Purpose\s*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    purpose = match.group(1).strip() if match else ""
    if not purpose or purpose.startswith("What this restaurant exists to achieve"):
        raise BrigadeError("menu.md has no purpose yet; write the Purpose section before briefing a worker")
    return purpose


def attempt_kind(events, ident):
    kind = "first"
    for event in events:
        if event["kind"] == "dish" and event["id"] == ident:
            kind = ATTEMPT_AFTER.get(event["state"], kind)
    return kind


@dataclass(frozen=True)
class ModeInputs:
    project_root: str
    station: str
    attempt: str
    paths: str
    send_backs: int
    coordinator: str
    escalated: str
    dish: dict
    thread: str
    generation: int


@dataclass(frozen=True)
class ModeLines:
    lines: tuple
    mode: str
    escalation: str


def brief_dish(restaurant, ident, paths, lease, acceptance):
    _, dish = restaurant.find("dishes.tsv", ident)
    refusal = fix_round_refusal(restaurant, dish)
    if refusal:
        raise BrigadeError(refusal)
    paths, lease = paths or dish.get("paths", ""), lease or dish.get("lease", "")
    if not paths or not lease:
        raise BrigadeError(f"{ident} has no lease; fire with --paths, or pass --paths and --lease")
    if not acceptance:
        raise BrigadeError("a brief needs at least one --acceptance criterion")
    if dish["state"] not in ("in-progress", "sent-back"):
        raise BrigadeError(f"{ident} is {dish['state']}; brief a dish that is in progress or sent back")
    thread = (restaurant.meta.get("thread") or "").strip()
    if not thread:
        raise BrigadeError("no coordinator thread recorded; run brigade.py set --thread")
    menu_purpose(restaurant)
    return dish, paths, lease, thread


def mode_inputs(restaurant, dish, paths, thread):
    meta = restaurant.meta
    events = restaurant.rows("log.tsv")
    sent_back = len(send_backs(restaurant.rows("pass.tsv"), dish["id"]))
    return ModeInputs(meta["projectRoot"], dish["station"], attempt_kind(events, dish["id"]), paths, sent_back,
                      meta.get("mode") if meta.get("mode") in MODES else None, latest_mode_note(events, dish["id"]),
                      dish, thread, meta.get("generation"))


def roles_script():
    for path in (BUILT_ROLES, SOURCE_ROLES):
        if path.is_file():
            return path
    raise BrigadeError(f"cannot find roles.py at {BUILT_ROLES} or {SOURCE_ROLES}; build or reinstall pstack-t3")


def roles_mode(inputs):
    if HELD_LOCKS:
        raise BrigadeError(f"roles.py may run git; release {HELD_LOCKS[0]}'s store lock before resolving the mode")
    argv = [sys.executable, str(roles_script()), "mode", "--cwd", inputs.project_root, "--paths", inputs.paths,
            "--send-backs", str(inputs.send_backs)]
    if inputs.coordinator:
        argv += ["--coordinator-mode", inputs.coordinator]
    if inputs.escalated is not None:
        argv += ["--escalated", inputs.escalated]
    result = subprocess.run(argv + ["--playbook", inputs.station, "--attempt", inputs.attempt], capture_output=True, text=True)
    if result.returncode and "unknown playbook" in result.stderr:
        result = subprocess.run(argv, capture_output=True, text=True)
    if result.returncode:
        raise BrigadeError(f"roles.py mode refused the brief: {result.stderr.strip().removeprefix('error: ')}")
    lines = tuple(result.stdout.splitlines())
    modes = [line.removeprefix("Mode: ") for line in lines if line.startswith("Mode: ")]
    if len(modes) != 1 or modes[0] not in MODES:
        raise BrigadeError("roles.py mode printed no Mode: full or Mode: light line")
    source = next((line.removeprefix("Mode source: ") for line in lines if line.startswith("Mode source: ")), "")
    return ModeLines(lines, modes[0], source.removeprefix(ESCALATED) if source.startswith(ESCALATED) else None)


def brief(restaurant, ident, goal, acceptance, verify, paths, lease, base, context):
    for _ in range(MODE_RESOLUTIONS):
        with restaurant.checked():
            restaurant.fence()
            dish, used_paths, _, thread = brief_dish(restaurant, ident, paths, lease, acceptance)
            inputs = mode_inputs(restaurant, dish, used_paths, thread)
        mode = roles_mode(inputs)
        with restaurant.checked():
            restaurant.fence()
            dish, used_paths, used_lease, thread = brief_dish(restaurant, ident, paths, lease, acceptance)
            if mode_inputs(restaurant, dish, used_paths, thread) != inputs:
                continue
            if inputs.escalated is None and mode.escalation:
                record_escalation(restaurant, ident, mode.escalation)
            return write_brief(restaurant, dish, mode, goal, acceptance, verify, used_paths, used_lease, base, context, thread)
    raise BrigadeError(f"{ident} changed while resolving its mode; run brief again")


def write_brief(restaurant, dish, mode, goal, acceptance, verify, paths, lease, base, context, thread):
    ident = dish["id"]
    if not dish["branch"]:
        dish = restaurant.update("dishes.tsv", ident, "dish", branch=f"{slug(restaurant.meta['restaurant'])}/{ident.lower()}")
    tickets = {row["id"]: row for row in restaurant.rows("rail.tsv")}
    land = LAND
    report = restaurant.dir / "reports" / f"{ident}.md"
    sent_back = send_backs(restaurant.rows("pass.tsv"), ident)
    findings = restaurant.dir / "reports" / (sent_back[-1]["report"] if sent_back and sent_back[-1]["report"] else f"{ident}-review.md")
    lines = [
        f"Use the poteto-mode skill and its `{dish['station']}` playbook.", *mode.lines, "Gate: brigade", SEAT_RULE, "",
        f"GOAL: {goal}",
        f"PURPOSE: {menu_purpose(restaurant)}",
        f"TICKETS: " + "; ".join(f"{t}: {tickets[t]['summary']}" for t in dish["tickets"].split(",") if t in tickets), "",
        "SCOPE:",
        f"- You run in your own git worktree on branch `{dish['branch']}`, started from `{base}`. Work only there, and commit on that branch.",
        f"- Change only these paths, leased to you as {lease}: {paths}. A change outside them is refused when it lands. Report it instead of making it.",
        "- Keep history linear: no merge commits. Never merge, rebase a shared branch, push trunk, or open a PR. The landing queue does that.",
        "", "CONTEXT:", *([f"- {item}" for item in context] or ["- None beyond the tickets."]),
        *([f"- A reviewer sent an earlier attempt back. Its findings: {findings}"] if findings.exists() else []),
        "", "ACCEPTANCE:", *[f"- {item}" for item in acceptance],
        "", "VERIFY:", f"- {verify}",
        f"- Run builds and tests through `python3 {land} slot -- <command>`.",
        *([f"- Run every measurement through `python3 {land} slot --exclusive -- <command>`, so no other work shares the machine while it runs."]
          if dish["station"] in MEASURING_STATIONS else []),
        "", f"TIMEBOX: {dish.get('timebox') or 60} minutes. The timebox orders the work and never waives a playbook step (How, Architect, investigation, or the implementation delegate). At the limit, write the report with what remains instead of skipping steps.",
        "", "REPORT:",
        WAIT_RULE,
        f"- Write it to {report}: status, branch, head SHA, what you ran and its output, before and after numbers with the method, deviations, follow-ups. "
        "List each follow-up as one top-level list item under a `## Follow-ups` heading, or write `None.` there.",
        "- Under the status line, repeat this brief's Mode: line, and its Waived by mode: line when it has one. A step that line names is not a deviation.",
        *(["- If you find the design contested, do not run interrogate. Stop at a verifiable point, commit, and write Contested: <one-line reason> under the status line. The coordinator moves the work to full mode and gives your report to a fresh worker."]
          if mode.mode == "light" else []),
        f"- After that file is written, call t3_thread_send to thread {thread} with mode \"auto\" and the one-line message \"{ident} done: report at {report}\".",
        "- Then end your turn with one line naming the report path.",
        "", "STANDING ORDERS:", (restaurant.dir / "house-rules.md").read_text().strip(),
    ]
    text = "\n".join(lines) + "\n"
    restaurant.write(Path("briefs") / f"{ident}.md", text)
    return text


def attempt_starts(restaurant, dish):
    """When each attempt started: the dish's in-progress log rows, oldest first.

    Replacing the worker appends that row again without leaving in-progress.
    """
    moves = [row["at"] for row in restaurant.rows("log.tsv") if row["kind"] == "dish" and row["id"] == dish["id"] and row["state"] == "in-progress"]
    return [datetime.fromisoformat(at) for at in moves or [dish["at"]]]


def retired_worker_threads(restaurant, ident):
    """Worker thread ids this dish already used on an earlier attempt."""
    return [row["note"] for row in restaurant.rows("log.tsv")
            if row["kind"] == "worker" and row["id"] == ident and row["state"] == "retired" and row["note"]]


def renew_line(restaurant, dish):
    """Renew a live lease. Returns the line to print, or None, and whether the landing store answered."""
    lease = dish["lease"]
    result = land_result(restaurant.meta["projectRoot"], "lease", "renew", lease, "--if-live", *restaurant.land_owner())
    error = result.stderr.strip().removeprefix("land: ")
    if result.returncode == 0 or error.startswith(f"{lease} is submitted"):
        return None, True
    if error == f"{lease} is released":
        return f"{dish['id']}: lease {lease} was released; claim again before submitting", True
    if error.startswith(f"{lease} expired at "):
        return f"{dish['id']}: lease {lease} expired; stop its worker, then run lease renew {lease}", True
    return f"{dish['id']}: could not renew {lease}: {error or result.stdout.strip()}", False


ENTRY_LINE = re.compile(r"^E(\d+) (\S+) \((\S+), ([0-9a-f]+)\)(.*)$")


def entry_line(restaurant, dish):
    """The queue's entry for this dish: its holder's highest entry at exactly the dish's SHA.

    Returns the line to print, or None, and whether that entry holds the dish's submission.
    """
    sha = dish["sha"].lower()
    if not sha:
        return (None if dish["state"] == "passed" else f"{dish['id']}: queued, but no SHA recorded"), False
    result = land_result(restaurant.meta["projectRoot"], "status", "--holder", holder(restaurant, dish["id"]), "--sha", sha)
    if result.returncode != 0:
        return f"{dish['id']}: could not read the queue: {result.stderr.strip().removeprefix('land: ')}", False
    found = None
    for line in result.stdout.splitlines():
        found = ENTRY_LINE.match(line) or found
    if not found:
        return (None if dish["state"] == "passed" else f"{dish['id']}: queued, but no entry at {sha[:12]}"), False
    number, state, rest = found.group(1), found.group(2), found.group(5)
    ident = dish["id"]
    if state == "bounced":
        return f"{ident}: E{number} bounced{rest}", False
    if dish["state"] == "passed":
        return f"{ident}: E{number} already submitted; mark it queued", True
    if state == "landed":
        return f"{ident}: landed as E{number} ({rest.removeprefix(' as ')}); mark it merged", True
    if state == "awaiting-merge":
        return f"{ident}: E{number} awaiting merge {rest.strip()}; watch that PR", True
    return f"{ident}: E{number} {state}", True


def option_key(text):
    return text.strip().rstrip(".").casefold()


def closing_options(row):
    if not row.get("dish", "").strip():
        return []
    default = option_key(row.get("default", ""))
    options = []
    for option in row.get("options", "").split(","):
        option = option.strip()
        if option and option_key(option) != default:
            options.append(option)
    return options


def open_item_decisions(rows):
    decisions = {}
    for row in rows:
        dish = row["dish"]
        if row["state"] == "open" and dish and dish not in decisions:
            decisions[dish] = row
    return decisions


def watch(restaurant):
    rails = sibling_rails(restaurant)
    with restaurant.checked():
        restaurant.fence()
        progress = {}
        moment = datetime.now(timezone.utc)
        dishes = [dish for dish in restaurant.rows("dishes.tsv") if dish["state"] not in ("merged", "dropped")]
        decisions = open_item_decisions(restaurant.rows("86.tsv"))
        debts = {dish["id"]: round_debt(restaurant, dish) for dish in dishes}
        for dish in dishes:
            if dish["state"] != "in-progress":
                continue
            attempt = progress.setdefault(dish["id"], [])
            starts = attempt_starts(restaurant, dish)
            if not dish["thread"] and len(starts) > 1:
                attempt.append(f"{dish['id']}: in progress with no worker thread; launch a fresh worker")
                continue
            start = starts[-1]
            minutes = int((moment - start).total_seconds() // 60)
            timebox = int(dish.get("timebox") or 60)
            report = restaurant.dir / "reports" / f"{dish['id']}.md"
            where = f"thread {dish['thread']}" if dish["thread"] else (f"task {dish['task']}" if dish["task"] else "no worker recorded")
            written = datetime.fromtimestamp(report.stat().st_mtime, timezone.utc) if report.exists() else None
            if written and written >= start:
                if dish.get("reported") == "yes":
                    ago = int((moment - written).total_seconds() // 60)
                    if ago > OPEN_RUN_MINUTES:
                        attempt.append(f"{dish['id']}: reported {ago}m ago, not in review; read the thread ({where})")
                    else:
                        attempt.append(f"{dish['id']}: report written {ago}m ago; review it even if the worker's run is still open ({where})")
                else:
                    attempt.append(f"{dish['id']}: report written, no report-back ({where})")
            elif minutes > timebox:
                attempt.append(f"{dish['id']}: over its {timebox}m timebox at {minutes}m with no report; read its thread and decide ({where})")
            else:
                attempt.append(f"{dish['id']}: running {minutes}m of {timebox}m ({where})")
        lines = []
        for ticket in restaurant.rows("rail.tsv"):
            if ticket["state"] != "moved":
                continue
            name = ticket["dish"].removeprefix("to:")
            target = restaurant.dir.parent / name
            handoff = handoff_id(restaurant.dir, ticket["id"])
            taken = taken_row(rails.get(target.resolve()), handoff)
            # take writes the ticket before it deletes the file, so a missing file with no ticket was never delivered.
            if inbox_file(target, handoff).exists():
                if taken is None:
                    lines.append(f"{ticket['id']}: moved to {name}, waiting for ticket take")
            elif taken is None:
                lines.append(f"{ticket['id']}: moved to {name}, not delivered; run ticket move {ticket['id']} --to {name} again")
        handed = handed_count(restaurant)
        if handed:
            lines.append(f"handed to you: {handed}; run ticket take")
        inputs = block_inputs(restaurant)
    # land.py waits on the landing database, so every call runs outside the store lock.
    item_lines, answered = [], True
    for dish in dishes:
        decision = decisions.get(dish["id"])
        pending = debts[dish["id"]]
        found = [] if decision or pending else progress.get(dish["id"], [])
        entry, submitted = entry_line(restaurant, dish) if dish["state"] in ("passed", "queued") else (None, False)
        # A submitted entry owns the lease now, so a released lease is not a reason to claim again.
        if dish["lease"] and dish["state"] in LEASED_STATES and not submitted:
            line, ok = renew_line(restaurant, dish)
            answered = answered and ok
            found += [line] if line else []
        found += [entry] if entry else []
        if pending:
            item_lines.append(f"{dish['id']}: {debts[dish['id']]} send-backs, decision pending")
        if decision:
            item_lines.append(f"{dish['id']}: open decision {decision['id']}: {decision['question']}; "
                              f"launch no worker or verifier until 86 answer {decision['id']}")
        if decision or pending:
            item_lines += found
        else:
            item_lines += found or [f"{dish['id']}: {OPEN_LINES[dish['state']]}"]
    for ident, note, held in recheck_blocks(restaurant, inputs):
        lines.append(f"{ident}: {held[1]}" if held else f"{ident}: unblocked; run {fire_command(ident, note)}")
    if answered:
        # walk --stale-hours then measures whether this coordinator still keeps its leases alive.
        restaurant.change_meta(lastActivityAt=now())
    return "\n".join(item_lines + lines) or "no work in progress"


def drop(restaurant, ident, stopped):
    """Drop a dish and release its lease, only after its worker stopped. A requested interrupt is not a stop."""
    with restaurant.checked():
        restaurant.fence()
        _, dish = restaurant.find("dishes.tsv", ident)
        lease = dish["lease"] if dish["state"] not in ("merged", "dropped") else ""
        if lease and dish["thread"] and not stopped:
            raise BrigadeError(f"{ident} holds {lease} and its worker may still be running; "
                               "wait for its run with t3_thread_wait, then pass --stopped <run id>")
    if lease:
        result = land_result(restaurant.meta["projectRoot"], "lease", "release", lease, *restaurant.land_owner())
        error = result.stderr.strip().removeprefix("land: ")
        if result.returncode != 0 and not error.startswith(f"{lease} is not active"):
            raise BrigadeError(f"{ident} not dropped: could not release {lease}: {error}")
    with restaurant.checked():
        _, dish = restaurant.find("dishes.tsv", ident)
        evidence = [f"stopped {stopped}"] if stopped else []
        evidence += [f"released {lease}"] if lease else []
        note = f"{dish['summary']} ({'; '.join(evidence)})" if evidence else None
        restaurant.update("dishes.tsv", ident, "dish", note=note, state="dropped")
        rows = restaurant.rows("rail.tsv")
        back = [row for row in rows if row["state"] == "assigned" and row["dish"] == ident]
        for row in back:
            row["state"], row["dish"] = "waiting", ""
        if back:
            restaurant.save_rows("rail.tsv", rows)
        for row in back:
            restaurant.log("ticket", row["id"], "waiting", f"{row['summary']} (back from dropped {ident})")
    if back:
        return f"{ident} dropped; {', '.join(row['id'] for row in back)} waiting again"
    return f"{ident} dropped"


def lease_states(project_root):
    """Each held lease's state in the landing queue, active or submitted, by id."""
    result = land_result(project_root, "lease", "list")
    return dict(line.split()[:2] for line in result.stdout.splitlines() if line.startswith("L"))


def fragment_lines(restaurant, ident, branch):
    """The commands that lease the new branch's changelog fragment. They are printed, not run.

    land.py cannot add paths to a lease. A claim made here would stay unrecorded when a drop or a new owner
    wins the store between the claim and its record.
    """
    states = lease_states(restaurant.meta["projectRoot"])
    with restaurant.checked():
        dish = restaurant.find("dishes.tsv", ident)[1]
    lease, paths = dish["lease"], with_fragment(dish["paths"], branch)
    if not lease or dish["state"] in ("merged", "dropped") or paths == dish["paths"]:
        return None
    fragment = changelog_fragment(branch)
    if states.get(lease) == "submitted":
        return (f"{ident}: {lease} is submitted, so it cannot take {fragment}; the submitted commit lands as it is. "
                f"Run dish {ident} --branch {branch} again if its entry bounces")
    owner = " ".join(restaurant.land_owner())
    owner = f" {owner}" if owner else ""
    active = states.get(lease) == "active"
    lines = [f"{ident}: {lease} {'does not cover' if active else 'is not active, so nothing covers'} {fragment}; "
             "cover it with these commands:",
             f"  $L lease claim --holder {holder(restaurant, ident)} --paths {shlex.quote(paths)}{owner}",
             f"  $B dish {ident} --lease <new lease> --paths {shlex.quote(paths)}"]
    if active:
        lines.append(f"  $L lease release {lease}{owner}")
    return "\n".join(lines)


def next_owner(meta, thread, replace, expect=None, stopped=None):
    """The generation set --thread records, and whether it changes the recorded thread.

    The executive admin's thread changes only by compare-and-swap: --expect names the thread it replaces.
    """
    current = (meta.get("thread") or "").strip()
    generation = meta.get("generation")
    if expect is not None:
        if not is_admin(meta):
            raise BrigadeError("--expect works only in the executive admin's store")
        if not replace:
            raise BrigadeError("the executive admin's thread changes only with --replace --expect <old>")
        if current != expect:
            raise BrigadeError(f"thread is {current or 'not recorded'}, not {expect or 'empty'}; nothing replaced")
        if thread == current:
            return generation or 1, False
        if current.startswith("recovering:") and not stopped:
            raise BrigadeError(NOT_STOPPED)
        return (generation or 0) + 1, True
    if is_admin(meta) and (current or generation) and thread != current:
        raise BrigadeError("the executive admin's thread changes only with --replace --expect <old>")
    if current and thread != current:
        if not replace:
            raise BrigadeError(f"thread {current} already recorded")
        return (generation or 1) + 1, True
    return generation or 1, not current


def set_thread(restaurant, args):
    """Raise the landing floor first, outside the store lock, so a crash before the rewrite is reached again."""
    while True:
        with restaurant.locked():
            target = next_owner(restaurant.meta, args.thread, args.replace, args.expect, args.stopped)
        generation, changing = target
        if changing and generation > 1:
            prefix = holder_prefix(restaurant.meta)
            result = land_result(restaurant.meta["projectRoot"], "owner", "--prefix", prefix, "--generation", str(generation))
            error = result.stderr.strip().removeprefix("land: ")
            # A project with no landing contract has no leases to fence.
            if result.returncode != 0 and "has no landing contract" not in error and "not a git repository" not in error:
                raise BrigadeError(f"thread not replaced: could not raise the landing floor for {prefix}: {error}")
        with restaurant.checked():
            if next_owner(restaurant.meta, args.thread, args.replace, args.expect, args.stopped) != target:
                continue
            # Recording the same thread again is an ordinary write, so it keeps the fence.
            restaurant.unfenced = changing
            return command(restaurant, args)


def hang_attempt(row, starts):
    """The attempt a hang row belongs to: its `(attempt <n>)` suffix, or the attempt running when it was logged."""
    match = re.search(r" \(attempt (\d+)\)$", row["note"])
    if match:
        return int(match.group(1))
    return sum(start <= datetime.fromisoformat(row["at"]) for start in starts)


def record_hang(restaurant, ident, provider, minutes, attempt=None):
    if not clean(provider):
        raise BrigadeError("hang needs a provider")
    if minutes < 0:
        raise BrigadeError("minutes must be 0 or more")
    _, dish = restaurant.find("dishes.tsv", ident)
    starts = attempt_starts(restaurant, dish)
    current = len(starts)
    if attempt is not None and not 1 <= attempt <= current:
        raise BrigadeError(f"{ident} has attempts 1 to {current}")
    # An earlier attempt was replaced, so only the current one waits for its report-back.
    if attempt in (None, current) and dish.get("reported") != "yes":
        earlier = f"; for a run left open by an earlier attempt, pass --attempt {'1' if current == 2 else f'1 to {current - 1}'}"
        raise BrigadeError("no report-back on this attempt" + (earlier if current > 1 else ""))
    number = attempt or current
    for row in restaurant.rows("log.tsv"):
        if row["kind"] == "hang" and row["id"] == ident and hang_attempt(row, starts) == number:
            return f"{ident}: hang already recorded"
    suffix = f" (attempt {attempt})" if attempt else ""
    restaurant.log("hang", ident, "open", f"{provider} {minutes}m{suffix}")
    return f"{ident}: {provider} open {minutes}m{suffix}"


def display_root(path):
    path = Path(path)
    try:
        relative = path.relative_to(Path.home())
    except ValueError:
        return str(path)
    if not relative.parts:
        return "~"
    return "~/" + relative.as_posix()


def leases_for(listing, prefix):
    """Lease ids from one `lease list`, held under this store's prefix. A failed listing holds none."""
    if listing.returncode != 0:
        return []
    found = []
    for line in listing.stdout.splitlines():
        parts = line.split()
        if len(parts) < 3 or not re.fullmatch(r"L\d+", parts[0]):
            continue
        holder = parts[2]
        if holder.startswith(prefix):
            found.append(f"{parts[0]} ({holder.removeprefix(prefix)})")
    return found


def walk(root, stale_hours=24, repo=None):
    """Coordinators grouped by projectRoot. One land.py status and one lease list per root, outside any store lock."""
    wanted = str(Path(repo).resolve()) if repo is not None else None
    groups = {}
    for meta_path in sorted(root.glob("*/*/restaurant.json")):
        restaurant = Restaurant(meta_path.parent)
        project = restaurant.meta.get("projectRoot", "")
        if wanted is not None and project != wanted:
            continue
        groups.setdefault(project, []).append(restaurant)
    if not groups:
        if wanted is not None:
            return f"no restaurants for {wanted}"
        return f"no restaurants under {root}"
    lines = []
    for project in sorted(groups):
        # The executive admin comes first in its repository.
        coordinators = sorted(groups[project], key=lambda restaurant: (not is_admin(restaurant.meta),
                                                                       str(restaurant.dir / "restaurant.json")))
        status = land_result(project, "status")
        listing = land_result(project, "lease", "list")
        header = status.stdout.strip() if status.returncode == 0 else "no landing contract"
        lines.append(f"{display_root(project)}: {header}")
        for restaurant in coordinators:
            meta = restaurant.meta
            age = datetime.now(timezone.utc) - datetime.fromisoformat(meta["lastActivityAt"])
            idle = f", idle {int(age.total_seconds() // 3600)}h" if age.total_seconds() > stale_hours * 3600 else ""
            counts = status_line(restaurant)
            blocked = len(holding_blocks(restaurant))
            if blocked:
                counts = re.sub(r"(waiting tickets: \d+)", rf"\1 ({blocked} blocked)", counts, count=1)
            mode = f", mode {meta['mode']}" if meta.get("mode") else ""
            lines.append(f"  {meta['restaurant']} (reports {reporting_of(meta)}{mode}){idle}: {counts}")
            leases = leases_for(listing, holder_prefix(meta))
            lease_text = f", leases {', '.join(leases)}" if leases else ""
            lines.append(f"    thread {meta.get('thread') or 'not recorded'}{lease_text}")
            for question in (row for row in restaurant.rows("86.tsv") if row["state"] == "open"):
                lines.append(f"    {question['id']}: {question['question']}")
    return "\n".join(lines)


REQUEST_NOTE = re.compile(r"^to (\S+): (.*)$")


def admin_requests(admin):
    """Each request the admin recorded, as (id, coordinator directory name, line)."""
    found = []
    for row in admin.rows("log.tsv"):
        match = REQUEST_NOTE.match(row["note"]) if row["kind"] == "request" else None
        if match:
            found.append((row["id"], match.group(1), match.group(2)))
    return found


def send_request(admin, to, line):
    """Record the request in the admin's log, then publish it into the coordinator's inbox under the admin's lock."""
    name, sibling = sibling_named(admin, to)
    line = clean(line)
    if not line:
        raise BrigadeError("a request needs its line")
    ident = f"A{max((int(ident[1:]) for ident, _, _ in admin_requests(admin)), default=0) + 1}"
    admin.log("request", ident, "sent", f"to {name}: {line}")
    admin.publish(admin.dir.parent / name / "inbox" / f"{ident}.line", line + "\n")
    return f"{ident} for {name}; {tell(name, sibling)}"


def relayed(admin):
    """The rows sync copied, as {relay id: the coordinator's row}."""
    return {row["id"]: json.loads(row["note"]) for row in admin.rows("log.tsv") if row["kind"] == "relay"}


def finished_by_coordinator(admin):
    """Each coordinator's finished requests, read from its own log.tsv. Run it before the admin's lock, as sync reads."""
    names = {name for _, name, _ in admin_requests(admin)}
    return {name: finished_requests(Restaurant(admin.dir.parent / name)) for name in names
            if (admin.dir.parent / name / "restaurant.json").is_file()}


def republish(admin, finished):
    """Publish again each request whose file is gone and whose coordinator has no inbox-done row for it."""
    lines = []
    for ident, name, line in admin_requests(admin):
        path = admin.dir.parent / name / "inbox" / f"{ident}.line"
        if path.exists() or ident in finished.get(name, ()):
            continue
        admin.publish(path, line + "\n")
        lines.append(f"{ident} republished for {name}")
    return "\n".join(lines) or "nothing to republish"


def ruling_line(row):
    line = (f"{row['id']} {row['state']} {row['kind']} ({row['parties']}): {row['question']} "
            f"Decided by {row['rule']}: {row['decision']}.")
    return line + (f" Supersedes {row['supersedes']}." if row["supersedes"] else "")


def _ruling_note(row, replacer):
    """The log note for a ruling row's current state. replacer maps an id to the ruling that replaced it."""
    state = row["state"]
    if state == "in-force":
        return row["decision"]
    if state in ("superseded", "overruled"):
        return f"replaced by {replacer[row['id']]}"
    return f"{row['decision']} ({state})"


def unlogged_rulings(admin):
    """Each rulings.tsv row whose state is not the latest ruling event, as (id, state, note).

    rulings.tsv is the authority. A new in-force row comes before the row it replaces, which is the order a ruling command logs them.
    """
    rows = admin.rows("rulings.tsv")
    latest = {}
    for event in admin.rows("log.tsv"):
        if event["kind"] == "ruling":
            latest[event["id"]] = event["state"]
    replacer = {row["supersedes"]: row["id"] for row in rows if row["supersedes"]}
    pending = sorted((row for row in rows if latest.get(row["id"]) != row["state"]), key=lambda row: row["state"] != "in-force")
    return [(row["id"], row["state"], _ruling_note(row, replacer)) for row in pending]


def log_rulings(admin):
    """Append a ruling event for each rulings.tsv row the log does not yet record. A rerun appends nothing."""
    with admin.guarded():
        for ident, state, note in unlogged_rulings(admin):
            admin.log("ruling", ident, state, note)


def add_ruling(admin, kind, parties, question, rule, decision, supersedes="", ended="superseded"):
    """Record a ruling, and mark the one it replaces, in one rewrite of rulings.tsv. Recording comes before carrying out."""
    rows = admin.rows("rulings.tsv")
    if supersedes:
        old = next((row for row in rows if row["id"] == supersedes), None)
        if old is None:
            raise BrigadeError(f"no {supersedes} in rulings.tsv")
        if old["state"] in ("superseded", "overruled"):
            raise BrigadeError(f"{supersedes} is already {old['state']}; replace the ruling that replaced it")
        old["state"] = ended
    ident = admin.next_id("rulings.tsv")
    rows.append({"id": ident, "at": now(), "kind": kind, "parties": ", ".join(intake_list(parties)), "question": question,
                 "rule": rule, "decision": decision, "supersedes": supersedes, "state": "in-force"})
    admin.save_rows("rulings.tsv", rows)
    log_rulings(admin)
    return ident


def overrule(admin, ident, decision):
    _, old = admin.find("rulings.tsv", ident)
    return add_ruling(admin, old["kind"], old["parties"], old["question"], "user", decision, ident, ended="overruled")


def end_ruling(admin, ident, state):
    rows, row = admin.find("rulings.tsv", ident)
    if row["state"] == state:
        return f"{ident} {state}"
    if row["state"] != "in-force":
        raise BrigadeError(f"{ident} is {row['state']}; only an in-force ruling ends")
    row["state"] = state
    admin.save_rows("rulings.tsv", rows)
    log_rulings(admin)
    return f"{ident} {state}"


def log_rows(data, start):
    """The complete rows of a log.tsv snapshot that starts at byte start.

    Returns (offset, row) pairs, the byte just past the last newline consumed, and the offset of a malformed line or None.
    """
    rows, position = [], 0
    while (newline := data.find(b"\n", position)) >= 0:
        offset = start + position
        try:
            line = data[position:newline].decode()
        except UnicodeDecodeError:
            return rows, offset, offset
        if offset > 0:
            row = parse_row("log.tsv", line)
            if row is None:
                return rows, offset, offset
            rows.append((offset, row))
        position = newline + 1
    return rows, start + position, None


def sync(admin):
    """Copy each coordinator's new log.tsv rows into the admin's log as relay rows, once each.

    Each coordinator's bytes are copied under its shared lock. The admin's lock is taken only after that lock is
    released, so no command holds two stores' locks. A relay id is the coordinator's store path and the row's byte
    offset, which a tail repair never moves, so a rerun after a crash copies nothing twice.
    Returns the lines to print and the malformed-line failures.
    """
    cursors = admin.meta.get("cursors") or {}
    copied, failures = [], []
    for name in siblings(admin.dir, admin.meta.get("projectRoot")):
        directory = admin.dir.parent / name
        store = store_path(directory)
        start = int(cursors.get(store, 0))
        data = Restaurant(directory).snapshot("log.tsv", start)
        if data is None:
            continue
        rows, end, malformed = log_rows(data, start)
        copied.append((name, store, rows, end))
        if malformed is not None:
            failures.append(f"{store}/log.tsv at byte {malformed} is malformed; nothing past it relayed")
    lines = []
    with admin.guarded():
        have = relayed(admin)
        cursors = dict(admin.meta.get("cursors") or {})
        for name, store, rows, end in copied:
            for offset, row in rows:
                ident = f"{store}@{offset}"
                if ident in have:
                    continue
                admin.append("log.tsv", {"at": now(), "kind": "relay", "id": ident, "state": "copied",
                                         "note": json.dumps(row, separators=(",", ":"))})
                lines.append(f"{name} {row['at']} {row['kind']} {row['id']} {row['state']}: {row['note']}")
            # A sync that started later may have read further and moved this cursor already.
            cursors[store] = max(end, int(cursors.get(store, 0)))
        admin.change_meta(cursors=cursors, lastActivityAt=now())
    return "\n".join(lines), failures


def admin_sections(admin, since):
    """The admin's report adds the rulings recorded or changed since the last one, each coordinator's relayed
    events, and each coordinator's newest report."""
    events = [event for event in admin.rows("log.tsv") if event["at"] > since]
    changed = {event["id"] for event in events if event["kind"] == "ruling"}
    changed.update(ident for ident, _, _ in unlogged_rulings(admin))
    lines = []
    rulings = [row for row in admin.rows("rulings.tsv") if row["id"] in changed]
    if rulings:
        lines += ["## Rulings", "", *(f"- {ruling_line(row)}" for row in rulings), ""]
    by_store = {}
    for event in events:
        if event["kind"] == "relay":
            by_store.setdefault(event["id"].rpartition("@")[0], []).append(json.loads(event["note"]))
    blocks = []
    for name in siblings(admin.dir, admin.meta.get("projectRoot")):
        directory = admin.dir.parent / name
        closeouts = sorted((directory / "closeouts").glob("*.md"))
        rows = by_store.get(store_path(directory), [])
        if not rows and not closeouts:
            continue
        blocks += [f"### {name}", "", *(f"- {row['at']} {row['kind']} {row['id']} {row['state']}: {row['note']}" for row in rows)]
        blocks += [f"- Newest report: {closeouts[-1]}"] if closeouts else []
        blocks.append("")
    if blocks:
        lines += ["## From each coordinator", "", *blocks]
    return lines


def parser():
    top = argparse.ArgumentParser(prog="brigade.py", description=__doc__.splitlines()[0])
    top.add_argument("--store", help="store root (default $BRIGADE_STORE or $XDG_STATE_HOME/pstack-t3/brigade)")
    top.add_argument("--at", default=os.environ.get("BRIGADE_DIR"), help="restaurant directory (default $BRIGADE_DIR)")
    top.add_argument("--owner", help="<thread>@<generation> from status; every write in a store with a generation needs it")
    sub = top.add_subparsers(dest="command", required=True)

    p = sub.add_parser("open", help="create a restaurant, or print an existing one")
    p.add_argument("--project-root", required=True)
    p.add_argument("--name")
    p.add_argument("--admin", action="store_true", help="open the repository's executive admin at <project>/.admin; takes no --name")
    p.add_argument("--reporting", choices=REPORTING, default="milestones",
                   help="how often the coordinator replies (default: milestones)")
    p.add_argument("--intake", default="", help="comma-separated intake sources this coordinator owns, such as github")
    p.add_argument("--workers", type=int, help="how many dishes may be in progress or in review; missing reads as 2")
    p.add_argument("--mode", choices=MODES, help="this restaurant's light or full mode; missing leaves it to the roles files")

    p = sub.add_parser("set", help="record the head chef thread, a schedule id, or the reporting level")
    p.add_argument("--thread")
    p.add_argument("--replace", action="store_true", help="replace a recorded coordinator thread")
    p.add_argument("--expect", help="executive admin only: replace the thread only while it is still this value")
    p.add_argument("--stopped", help="with --expect recovering:<id>: the run id t3_thread_wait reported terminal, idle, or gone")
    p.add_argument("--reports-to", help="the executive admin's thread this coordinator reports to; \"\" clears it")
    p.add_argument("--schedule", action="append", default=[], metavar="NAME=ID")
    p.add_argument("--reporting", choices=REPORTING, help="how often the coordinator replies")
    p.add_argument("--intake", help="comma-separated intake sources this coordinator owns; replaces the list, and \"\" clears it")
    p.add_argument("--workers", type=int, help="how many dishes may be in progress or in review")
    p.add_argument("--mode", help="full or light from the next brief; \"\" leaves it to the roles files")

    p = sub.add_parser("ticket", help="add, list, update, move, or take tickets on the rail")
    t = p.add_subparsers(dest="action", required=True)
    a = t.add_parser("add")
    how = a.add_mutually_exclusive_group(required=True)
    how.add_argument("--summary")
    how.add_argument("--from-report", metavar="FILE",
                     help="an item report under reports/, such as reports/D2.md; files one waiting ticket per follow-up in it "
                          "and changes only the ticket table, the log, and lastActivityAt")
    a.add_argument("--dry-run", action="store_true", help="with --from-report: print what it would add; it changes no table and no log")
    a.add_argument("--source", default="user")
    a.add_argument("--ref", default="")
    a.add_argument("--request", default="", help="the admin request id this ticket carries out; refuses a second ticket for it")
    a.add_argument("--again", action="store_true",
                   help="with --source user and no --ref: add the ticket even when a waiting or assigned ticket of this store "
                        "has the same summary. Case, leading and trailing whitespace, and the length of a whitespace run "
                        "do not count")
    a = t.add_parser("list")
    a.add_argument("--state", choices=TICKET_STATES)
    a = t.add_parser("set")
    a.add_argument("id")
    a.add_argument("--state", choices=[state for state in TICKET_STATES if state != "moved"], required=True)
    a = t.add_parser("move", help="hand a waiting ticket to a sibling coordinator through its inbox")
    a.add_argument("id")
    a.add_argument("--to", required=True, help="the sibling's directory name")
    t.add_parser("take", help="file every ticket a sibling handed to this coordinator")

    p = sub.add_parser("fire", help="group tickets into one dish and assign it to a station")
    p.add_argument("--tickets", required=True, help="comma-separated ticket ids")
    p.add_argument("--station", required=True, help="the pstack playbook the worker runs")
    p.add_argument("--summary", required=True)
    for field in ("task", "thread", "branch"):
        p.add_argument(f"--{field}", default="")
    p.add_argument("--timebox", type=int, default=60, help="minutes before the liveness check flags the dish")
    p.add_argument("--paths", default="", help="paths the dish will change; fire claims a landing lease on them first")
    p.add_argument("--mode", help="full, to start the dish in full mode; needs --reason")
    p.add_argument("--reason", help="one line: why the dish runs in full mode")

    p = sub.add_parser("brief", help="render the worker brief for a dish; refuses when a field or the coordinator thread is missing")
    p.add_argument("id")
    p.add_argument("--fields", help="JSON file of brief fields, or - for stdin")
    p.add_argument("--goal", default=None, help="one sentence: the outcome")
    p.add_argument("--acceptance", action="append", default=[], help="a checkable criterion; repeatable, at least one")
    p.add_argument("--verify", default=None, help="exact commands that prove it, plus known gotchas")
    p.add_argument("--paths", default=None, help="leased paths, when fire did not claim them")
    p.add_argument("--lease", default=None, help="the landing lease id, when fire did not claim it")
    p.add_argument("--base", default=None, help="the trunk ref the worker's branch starts from, such as origin/main")
    p.add_argument("--context", action="append", default=[], help="a pointer to files, PRs, or upstream reports; repeatable")

    sub.add_parser("watch", help="liveness: which dishes have reports, are running, or are over their timebox")

    p = sub.add_parser("hang", help="record one open run after report-back, once per attempt")
    p.add_argument("id")
    p.add_argument("--attempt", type=int, help="an earlier attempt, counted from 1, whose run was left open")
    p.add_argument("--provider", required=True)
    p.add_argument("--minutes", type=int, required=True)

    p = sub.add_parser("dish", help="update a dish")
    p.add_argument("id")
    p.add_argument("--state", choices=DISH_STATES)
    for field in ("task", "thread", "branch", "pr", "sha"):
        p.add_argument(f"--{field}")
    p.add_argument("--timebox", type=int, help="minutes; raise it once for a worker that is still making progress")
    p.add_argument("--reported", action="store_true", help="record that this attempt's report-back arrived")
    p.add_argument("--lease", help="record a lease id claimed again")
    p.add_argument("--paths", help="record the paths that lease covers")
    p.add_argument("--stopped", help="with --state dropped: the run id t3_thread_wait reported terminal, or idle")
    p.add_argument("--mode", help="full, to move open work to full mode once; needs --reason")
    p.add_argument("--reason", help="one line: why the dish moves to full mode")

    p = sub.add_parser("pass", help="record or check a review verdict for a dish at a head SHA")
    t = p.add_subparsers(dest="action", required=True)
    a = t.add_parser("record")
    a.add_argument("dish")
    a.add_argument("--pr", default="", help="PR URL; omit for local-only work")
    a.add_argument("--sha", required=True)
    a.add_argument("--verdict", choices=VERDICTS, required=True)
    a.add_argument("--author", required=True, help="provider/model of the worker")
    a.add_argument("--verifier", required=True, help="provider/model of the reviewer")
    a.add_argument("--note", default="")
    a.add_argument("--same-family", action="store_true", help="allow it when no other family is runnable")
    a.add_argument("--report", default="", help="the round's findings file under reports/, such as D2-review-1.md")
    kind = a.add_mutually_exclusive_group()
    kind.add_argument("--member", action="store_true",
                      help="a panel member's row that does not carry the item's verdict; the dish is left as it is")
    kind.add_argument("--late", action="store_true",
                      help="a round found unrecorded after the dish moved on; the dish is left as it is")
    a = t.add_parser("check")
    a.add_argument("dish")
    a.add_argument("--sha", required=True)
    a.add_argument("--json", action="store_true", help="print verdict, author, verifier, note, and crossFamily of the latest row")

    p = sub.add_parser("86", help="park or answer a decision that needs the user")
    t = p.add_subparsers(dest="action", required=True)
    a = t.add_parser("add")
    a.add_argument("--question")
    a.add_argument("--options")
    a.add_argument("--default")
    a.add_argument("--dish", default="")
    a.add_argument("--round-budget", action="store_true",
                   help=f"with --dish: write the decision a dish owes at {ROUND_BUDGET} send-backs; takes no question, options, or default")
    a = t.add_parser("answer")
    a.add_argument("id")
    a.add_argument("--answer", required=True)
    t.add_parser("list")

    p = sub.add_parser("inbox", help="take handed tickets and the admin's requests, or finish a request")
    t = p.add_subparsers(dest="action", required=True)
    t.add_parser("take", help="file handed tickets and print each request file")
    a = t.add_parser("done", help="record a request as acted on and delete its file")
    a.add_argument("id")

    p = sub.add_parser("request", help="executive admin: publish a request line into a coordinator's inbox")
    p.add_argument("line", nargs="?")
    p.add_argument("--to", help="the coordinator's directory name")
    p.add_argument("--republish", action="store_true", help="publish again each request a crash left unwritten")

    p = sub.add_parser("rule", help="executive admin: record, overrule, end, or list rulings")
    t = p.add_subparsers(dest="action", required=True)
    a = t.add_parser("add")
    a.add_argument("--kind", choices=RULING_KINDS, required=True)
    a.add_argument("--parties", required=True, help="comma-separated coordinator names")
    a.add_argument("--question", required=True)
    a.add_argument("--rule", choices=RULING_RULES, required=True, help="the rule that decided it")
    a.add_argument("--decision", required=True)
    a.add_argument("--supersedes", default="", help="the ruling this one replaces")
    a = t.add_parser("overrule", help="record the user's ruling in place of this one")
    a.add_argument("id")
    a.add_argument("--decision", required=True)
    a = t.add_parser("set", help="record how a ruling ended")
    a.add_argument("id")
    a.add_argument("--state", choices=("done", "expired"), required=True)
    a = t.add_parser("list")
    a.add_argument("--state", choices=RULING_STATES)

    sub.add_parser("sync", help="executive admin: copy each coordinator's new log rows into this log")

    sub.add_parser("status", help="the thread line first, then counts, then reports to, mode, and owner when present")
    p = sub.add_parser("close", help="write the report of what changed since the last one")
    output = p.add_mutually_exclusive_group()
    output.add_argument("--dry-run", action="store_true")
    output.add_argument("--to-file", action="store_true",
                        help="print only the path of the written report, not its text")
    p = sub.add_parser("walk", help="every restaurant's counts and open decisions, grouped by repository")
    p.add_argument("--stale-hours", type=float, default=24)
    p.add_argument("--repo", help="print only this repository")
    return top


def _brief_fields(args):
    flagged = any(getattr(args, name) is not None for name in ("goal", "verify", "base", "paths", "lease")) or args.acceptance or args.context
    if args.fields is not None:
        if flagged:
            raise BrigadeError("use either --fields or the field flags, not both")
        if args.fields == "-":
            if sys.stdin.isatty():
                raise BrigadeError("brief fields: --fields - reads JSON from stdin")
            raw = sys.stdin.read()
        else:
            try:
                raw = Path(args.fields).read_text(encoding="utf-8")
            except OSError as error:
                raise BrigadeError(f"brief fields: {error}") from error
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as error:
            raise BrigadeError(f"brief fields: {error}") from error
        if not isinstance(payload, dict):
            raise BrigadeError("brief fields: JSON must be an object")
        allowed = {"goal", "acceptance", "verify", "base", "context", "paths", "lease"}
        lists = {"acceptance", "context"}
        unknown = [key for key in payload if key not in allowed]
        if unknown:
            raise BrigadeError(f"brief fields: unknown key {unknown[0]}")
        for key in ("goal", "acceptance", "verify", "base"):
            if key not in payload:
                raise BrigadeError(f"brief fields: missing {key}")
        for key, value in payload.items():
            if value is None:
                raise BrigadeError(f"brief fields: {key} is null")
            if key in lists:
                if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                    raise BrigadeError(f"brief fields: {key} must be a list of strings")
            elif not isinstance(value, str):
                raise BrigadeError(f"brief fields: {key} must be a string")
        return {
            "goal": payload["goal"],
            "acceptance": payload["acceptance"],
            "verify": payload["verify"],
            "paths": payload["paths"] if "paths" in payload else "",
            "lease": payload["lease"] if "lease" in payload else "",
            "base": payload["base"],
            "context": payload["context"] if "context" in payload else [],
        }
    if args.goal is None or args.verify is None or args.base is None:
        raise BrigadeError("brief needs --fields, or --goal, --verify, and --base")
    return {
        "goal": args.goal,
        "acceptance": args.acceptance,
        "verify": args.verify,
        "paths": args.paths or "",
        "lease": args.lease or "",
        "base": args.base,
        "context": args.context,
    }


def run(argv):
    args = parser().parse_args(argv)
    root = store_root(args.store)
    if args.command == "open":
        if args.admin and args.name:
            raise BrigadeError("open --admin takes no --name")
        if not args.admin and not args.name:
            raise BrigadeError("open needs --name, or --admin")
        require_workers(args.workers)
        restaurant, created = open_restaurant(root, args.project_root, args.name, args.reporting,
                                              intake_list(args.intake), args.workers, args.admin, args.mode)
        lines = [f"{'opened' if created else 'exists'} {restaurant.dir}"]
        meta = restaurant.meta
        thread = (meta.get("thread") or "").strip()
        if not created and thread:
            lines.append(f"thread {thread} already recorded")
        intake = meta.get("intake") or []
        if not created and args.intake and intake_list(args.intake) != intake:
            lines.append(f"intake stays {', '.join(intake) or 'empty'}; change it with set --intake")
        if not created and args.mode is not None and args.mode != meta.get("mode"):
            lines.append(f"mode stays {meta.get('mode') or 'unset'}; change it with set --mode")
        lines.extend(sibling_lines(restaurant))
        if siblings(restaurant.dir, restaurant.meta.get("projectRoot")) and not is_admin(meta):
            cap = repository_cap(restaurant.meta["projectRoot"])
            workers = worker_cap(restaurant.meta)
            if cap is not None and workers >= cap:
                lines.append(f"warning: workers {workers} is at or above the repository cap of {cap} while a sibling exists")
        return "\n".join(lines)
    if args.command == "walk":
        return walk(root, args.stale_hours, args.repo)
    if not args.at:
        raise BrigadeError("pass --at <restaurant dir> or set BRIGADE_DIR")
    restaurant = Restaurant(args.at, args.owner)
    admin = is_admin(restaurant.meta)
    if admin and args.command in WORK_COMMANDS:
        raise BrigadeError("the executive admin routes work and never runs it")
    if not admin and args.command in ADMIN_COMMANDS:
        raise BrigadeError(f"{args.command} works only in the executive admin's store")
    if args.command == "sync":
        # The admin's lock is taken only after each coordinator's read lock is released, so this runs outside checked.
        text, failures = sync(restaurant)
        if failures:
            if text:
                print(text)
            raise BrigadeError("\nbrigade: ".join(failures))
        return text or "nothing new"
    if args.command == "request" and args.republish:
        if args.to or args.line:
            raise BrigadeError("request --republish takes no --to or line")
        finished = finished_by_coordinator(restaurant)
        with restaurant.checked():
            return republish(restaurant, finished)
    if args.command == "status":
        # land.py can wait on the landing database, so the contract is read before the store lock.
        contract = contract_mode(restaurant.meta["projectRoot"])
        with restaurant.checked():
            return command(restaurant, args, contract)
    if args.command == "set" and (args.thread or args.expect is not None):
        if args.thread is None:
            raise BrigadeError("--expect needs --thread")
        return set_thread(restaurant, args)
    if args.command in ("fire", "dish"):
        args.reason = item_escalation(args.mode, args.reason)
        if args.reason and args.command == "dish" and args.state in ("queued", "merged", "dropped"):
            raise BrigadeError(f"--mode full needs open work; run --state {args.state} without it")
    if args.command == "dish" and args.state == "dropped":
        return drop(restaurant, args.id, args.stopped)
    if args.command == "brief":
        # A stalled stdin or file must not hold the store lock, so the fields are read and checked first.
        fields = _brief_fields(args)
        return brief(restaurant, args.id, **fields)
    if args.command == "fire":
        ids = [ident.strip() for ident in args.tickets.split(",") if ident.strip()]
        return fire(restaurant, ids, args.station, args.task, args.thread, args.branch, args.summary, args.timebox,
                    args.paths, args.reason)
    if args.command == "watch":
        return watch(restaurant)
    if args.command == "ticket" and args.action == "list":
        held = holding_blocks(restaurant)
        with restaurant.checked():
            return ticket_lines(restaurant, args.state, held)
    if args.command == "dish" and args.branch and args.lease is None:
        with restaurant.checked():
            result = command(restaurant, args)
        lines = fragment_lines(restaurant, args.id, args.branch)
        return f"{result}\n{lines}" if lines else result
    if args.command == "ticket" and args.action == "add" and args.from_report is not None:
        if args.source != "user" or args.ref or args.request or args.again:
            raise BrigadeError("--from-report takes no --source, --ref, --request, or --again")
        name = item_report(restaurant, args.from_report)
        try:
            found = follow_ups((restaurant.dir / "reports" / name).read_text(encoding="utf-8"))
        except UnicodeDecodeError as error:
            raise BrigadeError(f"reports/{name} is not UTF-8 text; nothing added") from error
        with restaurant.checked():
            return file_follow_ups(restaurant, name, found, not args.dry_run)
    if args.command == "ticket" and args.action == "add" and args.dry_run:
        raise BrigadeError("--dry-run needs --from-report")
    rails = None
    if args.command == "ticket" and (args.action == "move" or args.action == "add" and args.ref):
        rails = sibling_rails(restaurant)
    with restaurant.checked():
        return command(restaurant, args, rails=rails)


def command(restaurant, args, contract=None, rails=None):
    if args.command == "set":
        meta = restaurant.meta
        changes, drop = {}, []
        if args.intake is not None:
            changes["intake"] = set_intake(restaurant, intake_list(args.intake))["intake"]
        if args.thread is not None and (args.thread or args.expect is not None):
            current = (meta.get("thread") or "").strip()
            generation, changing = next_owner(meta, args.thread, args.replace, args.expect, args.stopped)
            changes.update(generation=generation, thread=args.thread)
            if changing and current and not current.startswith("recovering:"):
                changes["previousThread"] = current
            if changing and is_admin(meta):
                # The row is the transition record. A crash before the metadata write keeps the stop evidence, and a retry finds the row.
                note = f"replaced {current}" if current else ("restarted" if meta.get("generation") else "first thread")
                note += f"; stopped {clean(args.stopped)}" if args.stopped else ""
                ident = f"{args.thread}@{generation}"
                if not any(row["kind"] == "thread" and row["id"] == ident for row in restaurant.rows("log.tsv")):
                    restaurant.log("thread", ident, "recorded", note)
        if args.reporting:
            changes["reporting"] = args.reporting
        if args.workers is not None:
            require_workers(args.workers)
            changes["workers"] = args.workers
        if args.mode is not None:
            if args.mode in MODES:
                changes["mode"] = args.mode
            elif args.mode == "":
                drop.append("mode")
            else:
                raise BrigadeError('--mode takes full, light, or ""')
        if args.reports_to is not None:
            if clean(args.reports_to):
                changes["reportsTo"] = clean(args.reports_to)
            else:
                drop.append("reportsTo")
        if args.schedule:
            schedules = dict(meta.get("schedules") or {})
            for pair in args.schedule:
                if "=" not in pair:
                    raise BrigadeError(f"--schedule takes NAME=ID, got {pair!r}")
                name, ident = pair.split("=", 1)
                if ident:
                    schedules[name] = ident
                else:
                    schedules.pop(name, None)
            changes["schedules"] = schedules
        meta = restaurant.change_meta(drop, **changes)
        return json.dumps(meta, indent=2)

    if args.command == "inbox":
        if args.action == "take":
            return take_inbox(restaurant)
        return finish_request(restaurant, args.id)

    if args.command == "request":
        if not args.to or args.line is None:
            raise BrigadeError('request needs --to <coordinator> "<line>", or --republish')
        return send_request(restaurant, args.to, args.line)

    if args.command == "rule":
        if args.action != "list":
            # A ruling command killed before its log row left an event to write first.
            log_rulings(restaurant)
        if args.action == "add":
            return add_ruling(restaurant, args.kind, args.parties, clean(args.question), args.rule, clean(args.decision),
                              clean(args.supersedes))
        if args.action == "overrule":
            return overrule(restaurant, args.id, clean(args.decision))
        if args.action == "set":
            return end_ruling(restaurant, args.id, args.state)
        rows = [row for row in restaurant.rows("rulings.tsv") if not args.state or row["state"] == args.state]
        return "\n".join(ruling_line(row) for row in rows) or "no rulings"

    if args.command == "ticket":
        if args.action == "add":
            return add_ticket(restaurant, args.summary, args.source, args.ref, args.request, rails or {}, again=args.again)
        if args.action == "move":
            return move_ticket(restaurant, args.id, args.to, rails or {})
        if args.action == "take":
            return "\n".join(take_tickets(restaurant)) or NOTHING_HANDED
        _, ticket = restaurant.find("rail.tsv", args.id)
        if ticket["state"] == "moved":
            raise BrigadeError(f"{args.id} moved to {ticket['dish'].removeprefix('to:')}; it is that coordinator's ticket now")
        restaurant.update("rail.tsv", args.id, "ticket", state=args.state)
        return f"{args.id} {args.state}"

    if args.command == "dish":
        _, current = restaurant.find("dishes.tsv", args.id)
        worker = any(value and value != current.get(field, "") for field, value in (("thread", args.thread), ("task", args.task)))
        if args.state == "in-progress" or worker:
            refusal = fix_round_refusal(restaurant, current)
            if refusal:
                raise BrigadeError(refusal)
        if args.state in COUNTED_STATES and current["state"] not in COUNTED_STATES:
            full = workers_full(restaurant)
            if full:
                raise BrigadeError(full)
        if (args.lease or args.paths) and current["state"] in ("merged", "dropped"):
            raise BrigadeError(f"{args.id} is {current['state']}; it holds no lease")
        if args.state in ("queued", "merged"):
            ok, why = pass_check(restaurant, args.id, args.sha or current["sha"])
            if not ok:
                raise BrigadeError(f"only reviewed work lands: {why}")
        entering = args.state == "in-progress" and current["state"] != "in-progress"
        restart = entering and current["state"] in ("sent-back", "queued")
        replacing = (bool(args.thread) and args.thread != current.get("thread", "")
                     and current["state"] == "in-progress" and args.state in (None, "in-progress"))
        thread = "" if restart and args.thread is None else args.thread
        recorded = set(retired_worker_threads(restaurant, args.id))
        earlier = set(recorded)
        if restart and current.get("thread"):
            earlier.add(current["thread"])
        if thread and thread in earlier:
            raise BrigadeError(f"thread {thread} is an earlier attempt of {args.id}; a send-back launches a fresh worker")
        escalated = None
        if args.reason:
            escalated = record_escalation(restaurant, args.id, args.reason)
        next_thread = current.get("thread", "") if thread is None else thread
        if current.get("thread") and next_thread != current["thread"] and (restart or next_thread):
            if current["thread"] not in recorded:
                restaurant.log("worker", args.id, "retired", current["thread"])
        reported = "" if entering or replacing else ("yes" if args.reported else None)
        row = restaurant.update("dishes.tsv", args.id, "dish", state=args.state, task=args.task, thread=thread,
                                branch=args.branch, pr=args.pr, sha=args.sha, timebox=args.timebox, reported=reported,
                                lease=args.lease, paths=args.paths)
        if replacing:
            restaurant.log("dish", args.id, "in-progress", row.get("summary", ""))
        if args.state == "merged":
            for ticket in filter(None, row["tickets"].split(",")):
                restaurant.update("rail.tsv", ticket, "ticket", state="done")
        if escalated is not None:
            return f"{args.id} {row['state']}, mode full: {escalated}"
        return f"{args.id} {row['state']}"

    if args.command == "pass":
        if args.action == "record":
            return record_pass(restaurant, args.dish, args.pr, args.sha, args.verdict, args.author, args.verifier,
                               args.note, args.same_family, args.report, args.member, args.late)
        ok, why = pass_check(restaurant, args.dish, args.sha)
        latest = latest_verdict(restaurant, args.dish, args.sha) if args.json else None
        if latest is not None:
            if ok:
                return pass_json(latest)
            print(pass_json(latest))
        if not ok:
            raise BrigadeError(why)
        return why

    if args.command == "86":
        if args.action == "add":
            given = [value for value in (args.question, args.options, args.default) if value is not None]
            if args.round_budget:
                if given or not args.dish:
                    raise BrigadeError("86 add --round-budget takes --dish and no --question, --options, or --default")
                restaurant.find("dishes.tsv", args.dish)
            elif len(given) < 3:
                raise BrigadeError("86 add needs --question, --options, and --default")
            open_row = open_item_decisions(restaurant.rows("86.tsv")).get(args.dish)
            if open_row:
                if args.round_budget and open_row["kind"] != ROUND_KIND:
                    raise BrigadeError(f"{args.dish} is held by {open_row['id']}; answer it, "
                                       f"then run 86 add --dish {args.dish} --round-budget")
                return open_row["id"]
            if args.round_budget:
                args.question, args.options, args.default = round_decision(restaurant, args.dish)
            # Validate the text the row will store, since the append turns tabs and newlines into spaces.
            question, options, default = clean(args.question), clean(args.options), clean(args.default)
            if args.dish:
                keys = {option_key(option) for option in options.split(",") if option.strip()}
                if option_key(default) not in keys or len(keys) < 2:
                    raise BrigadeError("an item decision's default must be one of its options, "
                                       "with at least one other option that closes it")
            ident = restaurant.next_id("86.tsv")
            restaurant.append("86.tsv", {"id": ident, "at": now(), "state": "open", "dish": args.dish,
                                         "question": question, "options": options, "default": default,
                                         "kind": ROUND_KIND if args.round_budget else ""})
            restaurant.log("decision", ident, "open", question)
            return ident
        if args.action == "answer":
            _, row = restaurant.find("86.tsv", args.id)
            if not row["dish"].strip():
                restaurant.update("86.tsv", args.id, "decision", state="answered", answer=args.answer, answered=now())
                return f"{args.id} answered"
            if row["state"] == "answered":
                return f"{args.id} answered"
            closes = closing_options(row)
            if not closes:
                restaurant.update("86.tsv", args.id, "decision", state="answered", answer=args.answer, answered=now())
                return f"{args.id} answered"
            match = next((option for option in closes if option_key(option) == option_key(args.answer)), None)
            if match is None:
                quoted = " or ".join(shlex.quote(option) for option in closes)
                return f"{args.id} still open; {row['dish']} stays held until 86 answer {args.id} --answer {quoted}"
            restaurant.update("86.tsv", args.id, "decision", state="answered", answer=match, answered=now())
            return f"{args.id} answered"
        lines = []
        for row in restaurant.rows("86.tsv"):
            if row["state"] != "open":
                continue
            label = f"{row['id']} for {row['dish']}" if row["dish"] else row["id"]
            lines.append(f"{label}: {row['question']} Options: {row['options']}. Default: {row['default']}.")
        return "\n".join(lines) or "no open decisions"

    if args.command == "hang":
        return record_hang(restaurant, args.id, args.provider, args.minutes, args.attempt)
    if args.command == "status":
        meta = restaurant.meta
        thread = (meta.get("thread") or "").strip()
        level = f"reporting: {reporting_of(meta)}, {contract}"
        counts_text = status_line(restaurant)
        # The thread comes first, so a service's fence step compares it before anything else.
        lines = [f"thread {thread}" if thread else "thread not recorded",
                 level if counts_text == "nothing on record" else f"{level}, {counts_text}"]
        if meta.get("reportsTo"):
            lines.append(f"reports to {meta['reportsTo']}")
        if meta.get("mode"):
            lines.append(f"mode {meta['mode']}")
        if meta.get("generation") is not None:
            lines.append(f"owner {thread}@{meta['generation']}")
        return "\n".join(lines)
    if args.command == "close":
        if not args.dry_run and is_admin(restaurant.meta):
            log_rulings(restaurant)
        text, path = report(restaurant, write=not args.dry_run)
        for name in unrecorded_reviews(restaurant):
            dish = name.split("-")[0]
            print(f"brigade: warning: reports/{name} has no review row; record it with pass record {dish} --report {name}, "
                  f"and --late when {dish} has moved past that round", file=sys.stderr)
        if args.to_file:
            return str(path.resolve())
        return text
    raise BrigadeError(f"unknown command {args.command}")


def main(argv=None):
    try:
        print(run(sys.argv[1:] if argv is None else argv))
    except BrigadeError as error:
        print(f"brigade: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
