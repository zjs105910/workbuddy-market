import fcntl
import io
import json
import os
import runpy
import shlex
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "t3/added/brigade/scripts/brigade.py"
CODEX = "codex/gpt-6.1-sol"
CLAUDE = "claudeAgent/claude-opus-5-5"
HELD_QUESTION = "D1: grok could not pass the seat's options: refused. Move this coordinator to a provider that passes them?"
HELD_LINE = (
    "D1: open decision Q1: D1: grok could not pass the seat's options: refused. "
    "Move this coordinator to a provider that passes them?; "
    "launch no worker or verifier until 86 answer Q1"
)
STILL_OPEN = "Q1 still open; D1 stays held until 86 answer Q1 --answer moved"
ITEM_DECISION = (
    "brigade: an item decision's default must be one of its options, "
    "with at least one other option that closes it"
)


def _wait_for_path(path, timeout=8):
    end = time.monotonic() + timeout
    while not path.exists():
        if time.monotonic() > end:
            raise TimeoutError(path)
        time.sleep(0.005)


def _shown_root(path):
    """The project root walk prints, with the home directory as ~."""
    path = Path(path).resolve()
    try:
        relative = path.relative_to(Path.home())
    except ValueError:
        return str(path)
    if not relative.parts:
        return "~"
    return "~/" + relative.as_posix()


def _owner_words(directory):
    """The --owner a coordinator reads from status, as the skill's service step 1 does."""
    try:
        meta = json.loads((Path(directory) / "restaurant.json").read_text())
    except (OSError, json.JSONDecodeError):
        return ()
    if not isinstance(meta, dict) or meta.get("generation") is None:
        return ()
    return ("--owner", f"{meta.get('thread') or ''}@{meta['generation']}")


def _race_child(mode, case, args):
    case = Path(case)
    if mode == "land-pause":
        land = runpy.run_path(str(ROOT / "t3/added/landing/scripts/land.py"))
        store = land["run"].__globals__["Store"]
        original_tx = store.tx

        def paused_tx(self):
            (case / "paused").touch()
            _wait_for_path(case / "proceed", timeout=60)
            return original_tx(self)

        store.tx = paused_tx
        sys.exit(land["main"](args))
    mod = runpy.run_path(str(SCRIPT))
    # run_path returns a copy. The live functions read the original globals.
    glob = mod["run"].__globals__
    if mode == "owner":
        original = glob["write_atomic"]

        def hooked(path, content):
            original(path, content)
            if Path(path).name == "restaurant.json":
                (case / "metadata-ready").touch()
                _wait_for_path(case / "owner-proceed")

        glob["write_atomic"] = hooked
    elif mode == "loser":
        original_wait = glob["wait_for_meta"]

        def hooked_wait(directory):
            meta = original_wait(directory)
            (case / "loser-saw-meta").touch()
            _wait_for_path(case / "loser-after-meta")
            return meta

        glob["wait_for_meta"] = hooked_wait
        original_write = glob["write_atomic"]

        def hooked_write(path, content):
            if Path(path).name in ("menu.md", "house-rules.md"):
                (case / "loser-at-scaffold").touch()
                _wait_for_path(case / "loser-scaffold-proceed")
            return original_write(path, content)

        glob["write_atomic"] = hooked_write
        original_save = glob["Restaurant"].save_rows

        def hooked_save(self, table, rows):
            if table == "rail.tsv" and rows == []:
                (case / "loser-at-scaffold").touch()
                _wait_for_path(case / "loser-scaffold-proceed")
            return original_save(self, table, rows)

        glob["Restaurant"].save_rows = hooked_save
    elif mode == "append":
        directory, label = args
        restaurant = glob["Restaurant"](directory)
        _wait_for_path(case / "go")
        for number in range(200):
            restaurant.append("log.tsv", {"at": glob["now"](), "kind": "ticket", "id": f"{label}{number}",
                                          "state": "waiting", "note": f"{label} row {number}"})
        sys.exit(0)
    elif mode == "die-before-publish":
        original = glob["write_atomic"]

        def hooked(path, content):
            if Path(path).parent.name == "inbox":
                os._exit(9)
            return original(path, content)

        glob["write_atomic"] = hooked
    elif mode == "fake-land":
        glob["LAND"] = case / "land.py"
    elif mode == "pause":
        original_locked = glob["Restaurant"].locked

        def paused_locked(self):
            if not getattr(self, "paused_once", False):
                self.paused_once = True
                (case / "paused").touch()
                _wait_for_path(case / "proceed", timeout=60)
            return original_locked(self)

        glob["Restaurant"].locked = paused_locked
    elif mode == "pause-after-finished":
        original_finished = glob["finished_by_coordinator"]

        def paused_finished(admin):
            finished = original_finished(admin)
            (case / "paused").touch()
            _wait_for_path(case / "proceed", timeout=60)
            return finished

        glob["finished_by_coordinator"] = paused_finished
    elif mode == "die-before-log":
        glob["Restaurant"].log = lambda self, *rest: os._exit(9)
    elif mode == "die-before-cursor":
        original_change = glob["Restaurant"].change_meta

        def dying_change(self, **fields):
            if "cursors" in fields:
                os._exit(9)
            return original_change(self, **fields)

        glob["Restaurant"].change_meta = dying_change
    elif mode == "die-before-thread":
        original_change = glob["Restaurant"].change_meta

        def dying_thread(self, drop=(), **fields):
            if "thread" in fields:
                os._exit(9)
            return original_change(self, drop, **fields)

        glob["Restaurant"].change_meta = dying_thread
    elif mode == "read16":
        reads = []

        def short_read(fd):
            data = os.read(fd, 16)
            if not reads:
                (case / "paused").touch()
                _wait_for_path(case / "proceed", timeout=60)
            reads.append(data)
            return data

        glob["read_chunk"] = short_read
    elif mode == "hold":
        original_append = glob["Restaurant"].append

        def holding_append(self, table, row):
            original_append(self, table, row)
            if table == "log.tsv" and not getattr(self, "held_once", False):
                self.held_once = True
                (case / "holding").touch()
                _wait_for_path(case / "proceed", timeout=60)

        glob["Restaurant"].append = holding_append
    elif mode == "brief-pause":
        original_roles = glob["roles_mode"]

        def paused_roles(inputs):
            lines = original_roles(inputs)
            if not (case / "paused").exists():
                (case / "paused").touch()
                _wait_for_path(case / "proceed", timeout=60)
            return lines

        glob["roles_mode"] = paused_roles
    elif mode == "brief-churn":
        original_roles = glob["roles_mode"]

        def churning_roles(inputs):
            lines = original_roles(inputs)
            path = Path(args[args.index("--at") + 1]) / "restaurant.json"
            meta = json.loads(path.read_text())
            meta["mode"] = "full" if meta.get("mode") == "light" else "light"
            path.write_text(json.dumps(meta))
            return lines

        glob["roles_mode"] = churning_roles
    elif mode == "append-row":
        directory, *fields = args
        restaurant = glob["Restaurant"](directory)
        restaurant.append("log.tsv", dict(zip(("at", "kind", "id", "state", "note"), fields)))
        sys.exit(0)
    elif mode == "die-inside-log-append":
        real_write = os.write

        def partial(fd, data):
            if b"\tfrom " in data:
                real_write(fd, data[:data.index(b"\tfrom ") + len(b"\tfro")])
                os._exit(9)
            return real_write(fd, data)

        os.write = partial
    else:
        raise SystemExit(f"unknown mode {mode}")
    sys.exit(mod["main"](args))


BULLETS = """# D1 report

Status: done

## Follow-ups

- A no-ref `--source user` add still has no CLI dedupe. The new Refusals rule tells the coordinator to read `ticket list` before refiling. A `brigade.py` guard would make that structural.
- `docs/guide.md` still describes intake as `gh issue list` and `gh pr list` when the standing orders name them. That file is outside this lease.
- PR #87 was not commented on, approved, or closed.
"""
NUMBERED = """## Follow-ups

1. **Hillclimb.** `t3/overrides/poteto-mode/playbooks/hillclimb.md` has a code-delegate line with the same missing step 5 pointer. It was outside the lease.
2. **`WAIT_RULE` in `t3/added/brigade/scripts/brigade.py`.** It states only the ten-minute clock for worker briefs. Decide whether it should point at the new step 5 bullet.
3. No README or `docs/guide.md` edit is needed.

Scratch is under `~/.cache/d87`.
"""
NESTED = """## Follow-ups

1. **D90-dependent wording.** These sentences hold for main and change if D90 lands:
   - Prompt caps step 1: "It still applies the Haiku prompt cap."
   - Step 4: the rerun of a seat-launching child on `inherit`.

   If D90 makes the flag skip capped models, step 1 should say the flag never returns a capped model.
2. **Docs batch.**
  - Change 4's Files list in `docs/light-mode.md` should add `t3/scripts/roles.py`.
  - `docs/light-mode.md` is not leased.
"""
FENCED = r"""## Follow-ups

1. Run this command to set the user's panel. It must use a fresh catalog.

   ```bash
   # write the panel
   python3 roles.py write --catalog <file> --keep \
     --set "review backups=opencode/step-5-preview-free?variant=high"
   ```

2. `family()` keeps the provider path for namespaced ids such as `opencode/...`. The panel compares bare ids locally.
"""
PROSE = """## Follow-ups

Schema setup in `land.py` still runs outside `BEGIN IMMEDIATE`.

`integration.head()` is still read inside two transactions.
Both sites predate this change.

No test under `tests/` asserts these sentences. That directory is outside this lease.

## Principles

- Fix root causes changed the order of the two reads.
"""
LEAD_IN = """## Follow-ups

The explainer found these in `brigade.py`. All are outside L81, so I did not fix them.

- `pass record` without `--pr` overwrites the item's recorded PR with an empty value, because `--pr` defaults to `""`.
- `--same-family` is not checked. It writes the `same model family;` note even when the families differ.
"""
TWO_SECTIONS = """# D1 report

## Follow-ups

1. `docs/light-mode.md`, in its review-file table, still describes one `<item>-review.md` file per item.
2. The panel sentences in step 7 still say "handle the send-back below" while that bullet sits above them.

## Decision trail

Kept in the store.

## Round 2

### Deviations

- None.

### Follow-ups

1. Decide whether `ticket move` should refuse a ticket of an item that owes its decision.

## Round 3

- The rule as implemented.
"""
PROSE_ABOVE_A_LEAD_IN = """## Follow-ups

**`README.md`.** Replace the `**Known limits.**` bullet (line 284), which still says "Nothing deletes it or moves it back", with these two bullets:

```markdown
- **Interrupted runs are recovered.** Every later install or uninstall looks in those directories.
- **Known limits.** Nothing returns or deletes it, so delete it by hand.
```

**`docs/guide.md`.** Replace the first bullet under "Known limits." (line 359) with this bullet, and keep the two bullets after it:

```markdown
- An entry in a `.pstack-t3-scrap-*` directory is an unfinished copy. Delete it by hand.
```

Other follow-ups:

- **Type the `side` that `holder_parents` yields**, from the comment review.
- **No test covers a skills directory inside the checkout**, which the sweep skips because `layout` refuses it.

Scratch files for this run are under `/tmp/d105-repro/`: `repro.py`, `before.txt`, and `full-suite.txt`.
"""
A_LIST_THEN_A_PROSE_SECTION = """## Follow-ups

1. `docs/light-mode.md`, in its review-file table, still describes one `<item>-review.md` file per item.

## Round 2

### Follow-ups

Schema setup in `land.py` still runs outside `BEGIN IMMEDIATE`.

`integration.head()` is still read inside two transactions.
"""
NO_WORK = """## Follow-ups

1. **Docs.** `README.md` and `docs/guide.md` do not mention the `recovered`, `removed`, and `left` lines.
2. None.
3. **None required.**
4. NONE NEEDED
5. _Nothing._
6. `Nothing needed`.
7. n/a
8. Not applicable.
9. **No follow-ups**.
"""
LONGER_THAN_A_NO_WORK_PHRASE = [
    "**No test covers a skills directory inside the checkout**, which the sweep now skips because `layout` refuses it.",
    "Docs. `README.md` and `docs/guide.md` do not name owner `queue` reports, so they need no change. The batched docs "
    "change could add a note to `docs/live-runs.md` that owners now use `auto`.",
    "`scripts/install.py` HARNESSES has no Muse entry. No Muse skills directory was confirmed, so nothing was added.",
    "The README roadmap and `docs/guide.md` do not name the script. No doc edit is needed unless the guide's release "
    "paragraph is touched.",
    "**Configure `escalate`.** The design lists `scripts/install.py` for this repository. None is set, so the trial ran "
    "light.",
    "None of the tests cover the retry path.",
    "Nothing in this change explains the release of lease L2.",
    "No lock is taken by `status`, though one is required.",
    "Decide whether `pass record --report` should refuse a path outside `reports/`, so it needs no second check.",
    "Add a test that verifies no edit is needed.",
    "No retry test exists and one is needed.",
    "None in the suite covers the retry path.",
    "None for `README.md` or `docs/guide.md`. They do not name this printed line.",
    "None required. The `changes/pstack-t3%2Fd57.md` fragment from the previous attempt still describes the change and "
    "was left as is.",
    "Nothing needed here until the guide's release paragraph moves.",
    "Not applicable. This lease holds no docs.",
    "No follow-ups for the docs batch, and one for the installer.",
    "Docs: none. No README or guide names the changed sentences.",
    "No README or `docs/guide.md` edit is needed.",
    "**No README or guide edit needed.** Neither file names these tools.",
    "`docs/guide.md` has no sentence about syncing upstream, so it needs no edit.",
]


class BrigadeTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.store = Path(self.temporary.name) / "store"
        self.project = Path(self.temporary.name) / "Bridge Kit"
        self.project.mkdir()
        self.at = self.store / "bridge-kit" / "perf"
        self.isolate_roles_config()

    def isolate_roles_config(self):
        patcher = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(Path(self.temporary.name) / "config")})
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.temporary.cleanup()

    def brigade(self, *args, ok=True, stdin=None, owner=True):
        return self.run_at(self.at, *args, ok=ok, stdin=stdin, owner=owner)

    def run_at(self, directory, *args, ok=True, stdin=None, owner=True):
        if owner and "--owner" not in args:
            args = (*_owner_words(directory), *args)
        result = subprocess.run([sys.executable, str(SCRIPT), "--store", str(self.store), "--at", str(directory), *args],
                                capture_output=True, text=True, input=stdin)
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        return (result.stdout if ok else result.stderr).strip()

    def table_row(self, directory, table, ident):
        lines = [line for line in (directory / table).read_text().splitlines() if line]
        keys = lines[0].split("\t")
        for line in lines[1:]:
            row = dict(zip(keys, line.split("\t")))
            if row["id"] == ident:
                return row
        self.fail(f"no {ident} in {directory / table}")

    def blocked_note(self, directory, ident):
        lines = [line for line in (directory / "log.tsv").read_text().splitlines() if line]
        keys = lines[0].split("\t")
        note = None
        for line in lines[1:]:
            row = dict(zip(keys, line.split("\t")))
            if row["kind"] == "ticket" and row["id"] == ident and row["state"] == "blocked":
                note = json.loads(row["note"])
        self.assertIsNotNone(note, ident)
        return note

    def bash_unblocked(self, directory, line):
        command = line.split("run ", 1)[1]
        invocation = " ".join([shlex.quote(sys.executable), shlex.quote(str(SCRIPT)),
                               "--store", shlex.quote(str(self.store)), "--at", shlex.quote(str(directory)),
                               command])
        return subprocess.run(["bash", "-c", invocation], capture_output=True, text=True, env=self.land_env())

    def open(self):
        return self.brigade("open", "--project-root", str(self.project), "--name", "Perf")

    def test_open_creates_the_store_once_and_keeps_edits(self):
        self.assertEqual(self.open(), f"opened {self.at}")
        (self.at / "menu.md").write_text("# Menu: Perf\n\nKeep startup under 400 ms.\n")
        self.assertEqual(self.open(), f"exists {self.at}")
        self.assertEqual((self.at / "menu.md").read_text(), "# Menu: Perf\n\nKeep startup under 400 ms.\n")
        self.assertIn("only through the repository's landing queue", (self.at / "house-rules.md").read_text())
        self.assertIn("Never use them in replies", (self.at / "house-rules.md").read_text())

    def test_fire_groups_waiting_tickets_into_one_dish(self):
        self.open()
        self.brigade("set", "--intake", "github")
        self.assertEqual(self.brigade("ticket", "add", "--summary", "Startup is slow on cold boot", "--source", "github", "--ref", "#12"), "T1")
        self.assertEqual(self.brigade("ticket", "add", "--summary", "Splash screen hangs"), "T2")
        self.assertEqual(self.brigade("fire", "--tickets", "T1,T2", "--station", "perf-issue", "--summary", "Cut cold start time"), "D1")
        self.assertEqual(self.brigade("ticket", "list"),
                         "T1 assigned [github] Startup is slow on cold boot #12\nT2 assigned [user] Splash screen hangs")
        self.assertEqual(self.brigade("fire", "--tickets", "T1", "--station", "bug-fix", "--summary", "again", ok=False),
                         "brigade: T1 is assigned, not waiting")

    def same_text_refusal(self, ticket, state):
        return f"brigade: same text as {ticket} ({state}); nothing added; pass --again to file a second ticket"

    def test_ticket_add_refuses_a_user_request_with_the_summary_of_a_waiting_ticket(self):
        self.open()
        self.assertEqual(self.brigade("ticket", "add", "--summary", "Fix the login page"), "T1")
        self.assertEqual(self.brigade("ticket", "add", "--summary", "fix  the LOGIN page", ok=False),
                         self.same_text_refusal("T1", "waiting"))
        self.assertEqual(self.brigade("ticket", "add", "--summary", "  Fix the\tlogin\npage  ", ok=False),
                         self.same_text_refusal("T1", "waiting"))
        self.assertEqual(self.brigade("ticket", "list"), "T1 waiting [user] Fix the login page")
        self.assertEqual(self.brigade("ticket", "add", "--summary", "Fix the loginpage"), "T2")
        self.assertEqual(self.brigade("ticket", "list"),
                         "T1 waiting [user] Fix the login page\nT2 waiting [user] Fix the loginpage")
        self.assertEqual(self.brigade("ticket", "add", "--summary", "fix  the LOGIN page", "--again"), "T3")

    def test_ticket_add_refuses_a_user_request_with_the_summary_of_an_assigned_ticket(self):
        self.open()
        self.brigade("ticket", "add", "--summary", "Fix the login page")
        self.brigade("fire", "--tickets", "T1", "--station", "bug-fix", "--summary", "Fix login")
        self.assertEqual(self.brigade("ticket", "add", "--summary", "Fix the login page", ok=False),
                         self.same_text_refusal("T1", "assigned"))

    def test_ticket_add_takes_a_user_request_with_the_summary_of_a_done_or_dropped_ticket(self):
        self.open()
        self.brigade("ticket", "add", "--summary", "Fix the login page")
        self.brigade("ticket", "set", "T1", "--state", "done")
        self.assertEqual(self.brigade("ticket", "add", "--summary", "Fix the login page"), "T2")
        self.brigade("ticket", "set", "T2", "--state", "dropped")
        self.assertEqual(self.brigade("ticket", "add", "--summary", "Fix the login page"), "T3")

    def test_ticket_add_names_a_waiting_ticket_of_another_source_with_the_same_summary(self):
        self.open()
        self.brigade("set", "--intake", "github")
        self.brigade("ticket", "add", "--summary", "Fix the login page", "--source", "github", "--ref", "#12")
        self.assertEqual(self.brigade("ticket", "add", "--summary", "Fix the login page", ok=False),
                         self.same_text_refusal("T1", "waiting"))

    def test_ticket_add_with_a_request_id_still_refuses_the_summary_of_a_waiting_ticket(self):
        self.open()
        self.brigade("ticket", "add", "--summary", "Fix the login page")
        self.assertEqual(self.brigade("ticket", "add", "--summary", "Fix the login page", "--request", "A2", ok=False),
                         self.same_text_refusal("T1", "waiting"))

    def test_ticket_add_with_a_ref_takes_the_summary_of_a_waiting_ticket(self):
        self.open()
        self.brigade("ticket", "add", "--summary", "Fix the login page")
        self.assertEqual(self.brigade("ticket", "add", "--summary", "Fix the login page", "--ref", "#12"), "T2")

    def test_again_lifts_neither_the_ref_refusal_nor_the_request_refusal_nor_the_source_refusal(self):
        self.open()
        self.brigade("ticket", "add", "--summary", "Fix the login page", "--ref", "#12", "--request", "A2")
        self.assertEqual(self.brigade("ticket", "add", "--summary", "Fix the login page", "--ref", "#12", "--again", ok=False),
                         "brigade: #12 is already T1 (waiting); nothing added")
        self.assertEqual(self.brigade("ticket", "add", "--summary", "Fix the login page", "--request", "A2", "--again", ok=False),
                         "brigade: request A2 is already T1; nothing added")
        self.assertEqual(self.brigade("ticket", "add", "--summary", "Fix the login page", "--source", "github", "--again", ok=False),
                         "brigade: no coordinator owns intake from github; the one that reads it runs set --intake github")
        self.assertEqual(self.brigade("ticket", "list"), "T1 waiting [user (request A2)] Fix the login page #12")

    def test_the_skill_quotes_the_same_summary_refusal_ticket_add_prints(self):
        self.open()
        self.brigade("ticket", "add", "--summary", "Fix the login page")
        line = self.brigade("ticket", "add", "--summary", "Fix the login page", ok=False)
        text = (ROOT / "t3/added/brigade/SKILL.md").read_text()
        section = text.split("## Filing tracker work", 1)[1].split("\n## ", 1)[0]
        step = next(row for row in section.splitlines() if row.startswith("4. **Refusals.**"))
        self.assertEqual(line, "brigade: same text as T1 (waiting); nothing added; pass --again to file a second ticket")
        self.assertIn("`" + line.replace("T1 (waiting)", "T<n> (<state>)") + "`", step)
        self.assertNotIn("never refused", step)

    def test_pass_refuses_a_verifier_from_the_author_family(self):
        self.open()
        self.brigade("ticket", "add", "--summary", "s")
        self.brigade("fire", "--tickets", "T1", "--station", "bug-fix", "--summary", "Fix s")
        error = self.brigade("pass", "record", "D1", "--pr", "u/1", "--sha", "abc", "--verdict", "pass",
                             "--author", CLAUDE, "--verifier", "cursor/claude-sonnet-5-5", ok=False)
        self.assertIn("same model family", error)
        self.assertEqual(self.brigade("pass", "record", "D1", "--pr", "u/1", "--sha", "abc", "--verdict", "pass",
                                      "--author", CLAUDE, "--verifier", "cursor/claude-sonnet-5-5", "--same-family"), "D1 passed")
        self.assertIn("same model family", (self.at / "pass.tsv").read_text())

    def test_queueing_or_merging_needs_a_pass_at_the_current_sha(self):
        self.open()
        self.brigade("ticket", "add", "--summary", "s")
        self.brigade("fire", "--tickets", "T1", "--station", "bug-fix", "--summary", "Fix s")
        self.brigade("pass", "record", "D1", "--pr", "u/1", "--sha", "abc", "--verdict", "pass", "--author", CLAUDE, "--verifier", CODEX)
        self.assertEqual(self.brigade("dish", "D1", "--state", "queued", "--sha", "def", ok=False),
                         "brigade: only reviewed work lands: D1 has no review verdict for def")
        self.assertEqual(self.brigade("dish", "D1", "--state", "queued"), "D1 queued")
        self.assertEqual(self.brigade("status"), "thread not recorded\nreporting: milestones, no landing contract, waiting to land: 1")
        self.assertEqual(self.brigade("dish", "D1", "--state", "merged"), "D1 merged")
        self.assertEqual(self.brigade("ticket", "list", "--state", "done"), "T1 done [user] s")

    def test_send_back_blocks_landing(self):
        self.open()
        self.brigade("ticket", "add", "--summary", "s")
        self.brigade("fire", "--tickets", "T1", "--station", "bug-fix", "--summary", "Fix s")
        self.brigade("pass", "record", "D1", "--pr", "u/1", "--sha", "abc", "--verdict", "send-back",
                     "--author", CLAUDE, "--verifier", CODEX, "--note", "test asserts the bug")
        self.assertEqual(self.brigade("pass", "check", "D1", "--sha", "abc", ok=False),
                         "brigade: D1 at abc: send-back (test asserts the bug)")
        self.assertEqual(self.brigade("dish", "D1", "--state", "queued", ok=False),
                         "brigade: only reviewed work lands: D1 at abc: send-back (test asserts the bug)")

    def check_json(self, sha):
        result = subprocess.run([sys.executable, str(SCRIPT), "--store", str(self.store), "--at", str(self.at),
                                 "pass", "check", "D1", "--sha", sha, "--json"], capture_output=True, text=True)
        return result.returncode, result.stdout, result.stderr.strip()

    def record(self, sha, verdict, *extra, author=CLAUDE, verifier=CODEX):
        self.brigade("pass", "record", "D1", "--sha", sha, "--verdict", verdict, "--author", author, "--verifier", verifier, *extra)

    def fired_bug_fix(self):
        self.open()
        self.brigade("ticket", "add", "--summary", "s")
        self.brigade("fire", "--tickets", "T1", "--station", "bug-fix", "--summary", "Fix s")

    def test_pass_check_json_prints_a_cross_family_pass(self):
        self.fired_bug_fix()
        self.record("abc", "pass")
        code, out, err = self.check_json("abc")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(json.loads(out), {"verdict": "pass", "author": CLAUDE, "verifier": CODEX, "note": "", "crossFamily": True})
        self.assertIn('"crossFamily": true', out)
        self.assertEqual(self.brigade("pass", "check", "D1", "--sha", "abc"), f"D1 at abc passed review by {CODEX}")

    def test_pass_check_json_exits_1_when_a_send_back_voids_the_pass(self):
        self.fired_bug_fix()
        self.record("abc", "pass")
        self.record("abc", "send-back", "--note", "test asserts the bug")
        code, out, err = self.check_json("abc")
        self.assertEqual((code, err), (1, "brigade: D1 at abc: send-back (test asserts the bug)"))
        self.assertIn('"verdict": "send-back"', out)
        self.assertEqual(json.loads(out)["note"], "test asserts the bug")

    def test_pass_check_json_marks_a_same_family_pass(self):
        self.fired_bug_fix()
        self.record("abc", "pass", "--same-family", verifier="cursor/claude-sonnet-5-5")
        self.record("def", "pass", "--same-family")
        with (self.at / "pass.tsv").open("a") as table:
            table.write(f"2026-10-08T00:00:00+00:00\tD1\t\tghi\tpass\t{CLAUDE}\tcursor/claude-sonnet-5-5\t\n")
        for sha, note in (("abc", "same model family;"), ("def", "same model family;"), ("ghi", "")):
            code, out, err = self.check_json(sha)
            self.assertEqual((code, err), (0, ""))
            self.assertIn('"crossFamily": false', out)
            self.assertEqual(json.loads(out)["note"], note)

    BEDROCK = "amazon-bedrock/us.anthropic.claude-sonnet-5-5-v1:0"
    NAMESPACED_MUSE = "opencode/opencode/muse-lite-2-free"

    def same_family_refusal(self, author, verifier):
        return (f"brigade: verifier {verifier} is the same model family as author {author}; "
                "pick a verifier from another family, or pass --same-family when no other family is runnable")

    def assert_one_family(self, author, verifier):
        self.fired_bug_fix()
        record = ("pass", "record", "D1", "--sha", "abc", "--verdict", "pass", "--author", author, "--verifier", verifier)
        self.assertEqual(self.brigade(*record, ok=False), self.same_family_refusal(author, verifier))
        self.assertEqual(self.pass_rows(), [])
        self.assertEqual(self.brigade(*record, "--same-family"), "D1 passed")
        self.assertEqual([row[5:8] for row in self.pass_rows()], [[author, verifier, "same model family;"]])

    def test_pass_record_refuses_a_bedrock_claude_author_with_a_claude_verifier(self):
        self.assert_one_family(self.BEDROCK, CLAUDE)

    def test_pass_record_refuses_an_underscored_claude_author_with_a_claude_verifier(self):
        self.assert_one_family("anthropic/claude_opus_5", "cursor/claude-sonnet-5-5")

    def test_pass_record_refuses_a_dated_claude_author_with_a_dated_claude_verifier(self):
        self.assert_one_family("vertex/claude-sonnet-5-5@20260101", "claudeAgent/claude-haiku-5-5-20260301")

    def test_pass_record_refuses_a_namespaced_muse_author_with_a_muse_verifier(self):
        self.assert_one_family(self.NAMESPACED_MUSE, "openrouter/muse-lite-2")

    def test_pass_record_records_two_families_with_no_flag(self):
        self.fired_bug_fix()
        for sha, author, verifier in (("abc", CLAUDE, CODEX), ("def", self.NAMESPACED_MUSE, CLAUDE)):
            self.assertEqual(self.brigade("pass", "record", "D1", "--sha", sha, "--verdict", "pass",
                                          "--author", author, "--verifier", verifier), "D1 passed")
        self.assertEqual([row[5:8] for row in self.pass_rows()], [[CLAUDE, CODEX, ""], [self.NAMESPACED_MUSE, CLAUDE, ""]])

    def test_pass_check_json_reads_a_stored_bedrock_row_as_one_family(self):
        self.fired_bug_fix()
        with (self.at / "pass.tsv").open("a") as table:
            table.write(f"2026-10-08T00:00:00+00:00\tD1\t\tabc\tpass\t{self.BEDROCK}\t{CLAUDE}\t\n")
        code, out, err = self.check_json("abc")
        self.assertEqual((code, err), (0, ""))
        self.assertIn('"crossFamily": false', out)

    def test_the_built_brigade_refuses_a_bedrock_claude_author_with_a_claude_verifier(self):
        self.fired_bug_fix()
        built = ROOT / "skills/brigade/scripts/brigade.py"
        result = subprocess.run([sys.executable, str(built), "--store", str(self.store), "--at", str(self.at),
                                 *_owner_words(self.at), "pass", "record", "D1", "--sha", "abc", "--verdict", "pass",
                                 "--author", self.BEDROCK, "--verifier", CLAUDE], capture_output=True, text=True)
        self.assertEqual((result.returncode, result.stdout), (1, ""))
        self.assertEqual(result.stderr.strip(), self.same_family_refusal(self.BEDROCK, CLAUDE))
        self.assertEqual(self.pass_rows(), [])

    def test_pass_record_without_roles_py_refuses_and_records_nothing(self):
        self.fired_bug_fix()
        glob = runpy.run_path(str(SCRIPT))["run"].__globals__
        missing = Path(self.temporary.name) / "missing"
        glob["BUILT_ROLES"], glob["SOURCE_ROLES"] = missing / "built.py", missing / "source.py"
        argv = ["--store", str(self.store), "--at", str(self.at), *_owner_words(self.at), "pass", "record", "D1",
                "--sha", "abc", "--verdict", "pass", "--author", CLAUDE, "--verifier", CODEX]
        with mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
            code = glob["main"](argv)
        self.assertEqual(code, 1)
        self.assertEqual(stderr.getvalue(), f"brigade: cannot find roles.py at {missing / 'built.py'} or "
                                            f"{missing / 'source.py'}; build or reinstall pstack-t3\n")
        self.assertEqual(self.pass_rows(), [])

    def test_pass_check_json_at_another_sha_has_no_verdict(self):
        self.fired_bug_fix()
        self.record("abc", "pass")
        self.assertEqual(self.check_json("def"), (1, "", "brigade: D1 has no review verdict for def"))

    def pass_rows(self):
        return [line.split("\t") for line in (self.at / "pass.tsv").read_text().splitlines()[1:]]

    def review_file(self, name, body="findings\n"):
        path = self.at / "reports" / name
        path.parent.mkdir(exist_ok=True)
        path.write_text(body)
        return path

    def dish_fields(self, *keys):
        row = self.table_row(self.at, "dishes.tsv", "D1")
        return tuple(row[key] for key in keys)

    def test_a_pass_table_holds_rows_written_before_and_after_the_report_and_member_columns(self):
        self.fired_bug_fix()
        stamp = "2026-10-08T00:00:00+00:00"
        old = f"{stamp}\tD1\t\tabc\tpass\t{CLAUDE}\t{CODEX}\told row"
        table = self.at / "pass.tsv"
        table.write_text("at\tdish\tpr\tsha\tverdict\tauthor\tverifier\tnote\n" + old + "\n"
                         + f"{stamp}\tD1\t\tdef\tsend-back\t{CLAUDE}\t{CODEX}\tnew row\tD1-review-2.md\t\n")
        self.assertEqual(self.brigade("pass", "check", "D1", "--sha", "abc"), f"D1 at abc passed review by {CODEX}")
        self.assertEqual(self.brigade("pass", "check", "D1", "--sha", "def", ok=False),
                         "brigade: D1 at def: send-back (new row)")
        self.record("ghi", "pass")
        self.assertEqual(table.read_text().splitlines()[1], old)
        self.assertEqual(self.pass_rows()[2][3:], ["ghi", "pass", CLAUDE, CODEX, "", "", ""])
        for fields, line in ((old.split("\t")[:7], 5), ([*old.split("\t"), "r.md", "", "extra"], 5)):
            table.write_text(table.read_text() + "\t".join(fields) + "\n")
            self.assertEqual(self.brigade("pass", "check", "D1", "--sha", "abc", ok=False),
                             f"brigade: pass.tsv line {line} is malformed; fix or remove it")
            table.write_text("\n".join(table.read_text().splitlines()[:-1]) + "\n")

    def test_pass_record_stores_the_bare_name_of_an_existing_review_report(self):
        self.fired_bug_fix()
        path = self.review_file("D1-review-1.md")
        self.review_file("D1-review.md")
        self.review_file("D1-review-2-panel-1.md")
        self.record("abc", "send-back", "--report", str(path))
        self.record("abc", "send-back", "--report", "reports/D1-review.md")
        self.record("abc", "send-back", "--report", "D1-review-2-panel-1.md")
        self.assertEqual([row[8] for row in self.pass_rows()], ["D1-review-1.md", "D1-review.md", "D1-review-2-panel-1.md"])
        before = (self.at / "pass.tsv").read_bytes()
        record = ("pass", "record", "D1", "--sha", "abc", "--verdict", "pass", "--author", CLAUDE, "--verifier", CODEX)
        self.assertEqual(self.brigade(*record, "--report", "D1-review-9.md", ok=False),
                         "brigade: reports/D1-review-9.md does not exist; write the review report first")
        self.review_file("D2-review-1.md")
        self.review_file("D1.md")
        self.review_file("D11-review.md")
        for name in ("D2-review-1.md", "D1.md", "D11-review.md"):
            self.assertEqual(self.brigade(*record, "--report", name, ok=False),
                             f"brigade: {name} is not a review report of D1; name a file like reports/D1-review-1.md")
        self.assertEqual((self.at / "pass.tsv").read_bytes(), before)
        self.assertEqual(self.dish_fields("state"), ("sent-back",))

    def store_files(self):
        """Every file of the store but restaurant.lock, which is empty and is not store data."""
        return {str(path.relative_to(self.at)): path.read_bytes() for path in sorted(self.at.rglob("*"))
                if path.is_file() and path.name != "restaurant.lock"}

    def tables(self):
        return {path.name: path.read_bytes() for path in sorted(self.at.glob("*.tsv"))}

    def follow_ups_in(self, body, *extra, name="D1.md", ok=True, owner=True):
        self.review_file(name, body)
        return self.brigade("ticket", "add", "--from-report", f"reports/{name}", *extra, ok=ok, owner=owner)

    def test_from_report_files_one_waiting_ticket_per_bullet_and_a_rerun_adds_nothing(self):
        self.fired_bug_fix()
        first = ("A no-ref `--source user` add still has no CLI dedupe. The new Refusals rule tells the coordinator to read "
                 "`ticket list` before refiling. A `brigade.py` guard would make that structural.")
        second = ("`docs/guide.md` still describes intake as `gh issue list` and `gh pr list` when the standing orders name "
                  "them. That file is outside this lease.")
        third = "PR #87 was not commented on, approved, or closed."
        self.assertEqual(self.follow_ups_in(BULLETS).splitlines(), [
            f"T2 added from perf/reports/D1.md#1: {first}",
            f"T3 added from perf/reports/D1.md#2: {second}",
            f"T4 added from perf/reports/D1.md#3: {third}",
        ])
        self.assertEqual(self.brigade("ticket", "list").splitlines()[-1],
                         f"T4 waiting [report] {third} perf/reports/D1.md#3")
        self.assertEqual(self.table_row(self.at, "rail.tsv", "T2")["summary"], first)
        self.assertIn(f"\tticket\tT4\twaiting\t{third}\n", (self.at / "log.tsv").read_text())
        before = (self.at / "rail.tsv").read_bytes()
        self.assertEqual(self.follow_ups_in(BULLETS).splitlines(), [
            f"skipped perf/reports/D1.md#1, same text as T2 (waiting): {first}",
            f"skipped perf/reports/D1.md#2, same text as T3 (waiting): {second}",
            f"skipped perf/reports/D1.md#3, same text as T4 (waiting): {third}",
        ])
        self.assertEqual((self.at / "rail.tsv").read_bytes(), before)
        self.brigade("ticket", "set", "T4", "--state", "dropped")
        self.brigade("ticket", "set", "T3", "--state", "done")
        before = (self.at / "rail.tsv").read_bytes()
        self.assertEqual(self.follow_ups_in(BULLETS).splitlines()[1:], [
            f"skipped perf/reports/D1.md#2, same text as T3 (done): {second}",
            f"skipped perf/reports/D1.md#3, same text as T4 (dropped): {third}",
        ])
        self.assertEqual((self.at / "rail.tsv").read_bytes(), before)

    def test_from_report_files_a_numbered_list_and_prints_the_paragraph_after_it(self):
        self.fired_bug_fix()
        self.assertEqual(self.follow_ups_in(NUMBERED, "--dry-run").splitlines(), [
            "would add from perf/reports/D1.md#1: **Hillclimb.** `t3/overrides/poteto-mode/playbooks/hillclimb.md` has a "
            "code-delegate line with the same missing step 5 pointer. It was outside the lease.",
            "would add from perf/reports/D1.md#2: **`WAIT_RULE` in `t3/added/brigade/scripts/brigade.py`.** It states only "
            "the ten-minute clock for worker briefs. Decide whether it should point at the new step 5 bullet.",
            "would add from perf/reports/D1.md#3: No README or `docs/guide.md` edit is needed.",
            "not filed, prose after the last list item: Scratch is under `~/.cache/d87`.",
        ])

    def test_from_report_files_prose_that_neither_introduces_a_list_nor_follows_the_last_item(self):
        self.fired_bug_fix()
        self.assertEqual(self.follow_ups_in(PROSE_ABOVE_A_LEAD_IN, "--dry-run").splitlines(), [
            "would add from perf/reports/D1.md#1: **`README.md`.** Replace the `**Known limits.**` bullet (line 284), "
            "which still says \"Nothing deletes it or moves it back\", with these two bullets: ```markdown "
            "- **Interrupted runs are recovered.** Every later install or uninstall looks in those directories. "
            "- **Known limits.** Nothing returns or deletes it, so delete it by hand. ```",
            "would add from perf/reports/D1.md#2: **`docs/guide.md`.** Replace the first bullet under \"Known limits.\" "
            "(line 359) with this bullet, and keep the two bullets after it: ```markdown - An entry in a "
            "`.pstack-t3-scrap-*` directory is an unfinished copy. Delete it by hand. ```",
            "would add from perf/reports/D1.md#3: **Type the `side` that `holder_parents` yields**, from the comment review.",
            "would add from perf/reports/D1.md#4: **No test covers a skills directory inside the checkout**, which the "
            "sweep skips because `layout` refuses it.",
            "not filed, prose that introduces a list: Other follow-ups:",
            "not filed, prose after the last list item: Scratch files for this run are under `/tmp/d105-repro/`: "
            "`repro.py`, `before.txt`, and `full-suite.txt`.",
        ])

    def test_from_report_files_the_prose_of_a_section_with_no_list_beside_a_section_with_one(self):
        self.fired_bug_fix()
        self.assertEqual(self.follow_ups_in(A_LIST_THEN_A_PROSE_SECTION, "--dry-run").splitlines(), [
            "would add from perf/reports/D1.md#1: `docs/light-mode.md`, in its review-file table, still describes one "
            "`<item>-review.md` file per item.",
            "would add from perf/reports/D1.md#2: Schema setup in `land.py` still runs outside `BEGIN IMMEDIATE`.",
            "would add from perf/reports/D1.md#3: `integration.head()` is still read inside two transactions.",
        ])

    def test_from_report_does_not_file_a_block_that_is_one_of_eight_no_work_phrases_and_nothing_more(self):
        self.fired_bug_fix()
        self.assertEqual(self.follow_ups_in(NO_WORK, "--dry-run").splitlines(), [
            "would add from perf/reports/D1.md#1: **Docs.** `README.md` and `docs/guide.md` do not mention the "
            "`recovered`, `removed`, and `left` lines.",
            "not filed, says no work is needed: None.",
            "not filed, says no work is needed: **None required.**",
            "not filed, says no work is needed: NONE NEEDED",
            "not filed, says no work is needed: _Nothing._",
            "not filed, says no work is needed: `Nothing needed`.",
            "not filed, says no work is needed: n/a",
            "not filed, says no work is needed: Not applicable.",
            "not filed, says no work is needed: **No follow-ups**.",
        ])

    def test_from_report_files_every_block_longer_than_a_no_work_phrase(self):
        self.fired_bug_fix()
        body = "## Follow-ups\n\n" + "".join(f"- {text}\n" for text in LONGER_THAN_A_NO_WORK_PHRASE)
        self.assertEqual(self.follow_ups_in(body, "--dry-run").splitlines(), [
            f"would add from perf/reports/D1.md#{number}: {text}"
            for number, text in enumerate(LONGER_THAN_A_NO_WORK_PHRASE, 1)])
        for text in LONGER_THAN_A_NO_WORK_PHRASE[-3:]:
            self.assertEqual(self.follow_ups_in(f"## Follow-ups\n\n{text}\n", "--dry-run"),
                             f"would add from perf/reports/D1.md#1: {text}")

    def test_from_report_folds_nested_bullets_and_an_indented_paragraph_into_their_item(self):
        self.fired_bug_fix()
        self.assertEqual(self.follow_ups_in(NESTED, "--dry-run").splitlines(), [
            "would add from perf/reports/D1.md#1: **D90-dependent wording.** These sentences hold for main and change if "
            "D90 lands: - Prompt caps step 1: \"It still applies the Haiku prompt cap.\" - Step 4: the rerun of a "
            "seat-launching child on `inherit`. If D90 makes the flag skip capped models, step 1 should say the flag never "
            "returns a capped model.",
            "would add from perf/reports/D1.md#2: **Docs batch.** - Change 4's Files list in `docs/light-mode.md` should "
            "add `t3/scripts/roles.py`. - `docs/light-mode.md` is not leased.",
        ])

    def test_from_report_keeps_a_fenced_block_in_its_item_and_reads_no_heading_inside_it(self):
        self.fired_bug_fix()
        self.assertEqual(self.follow_ups_in(FENCED, "--dry-run").splitlines(), [
            "would add from perf/reports/D1.md#1: Run this command to set the user's panel. It must use a fresh catalog. "
            "```bash # write the panel python3 roles.py write --catalog <file> --keep \\ "
            "--set \"review backups=opencode/step-5-preview-free?variant=high\" ```",
            "would add from perf/reports/D1.md#2: `family()` keeps the provider path for namespaced ids such as "
            "`opencode/...`. The panel compares bare ids locally.",
        ])

    def test_from_report_files_each_paragraph_of_a_section_with_no_list(self):
        self.fired_bug_fix()
        self.assertEqual(self.follow_ups_in(PROSE, "--dry-run").splitlines(), [
            "would add from perf/reports/D1.md#1: Schema setup in `land.py` still runs outside `BEGIN IMMEDIATE`.",
            "would add from perf/reports/D1.md#2: `integration.head()` is still read inside two transactions. "
            "Both sites predate this change.",
            "would add from perf/reports/D1.md#3: No test under `tests/` asserts these sentences. "
            "That directory is outside this lease.",
        ])

    def test_from_report_adds_nothing_for_a_section_that_says_none_or_a_report_without_one(self):
        self.fired_bug_fix()
        before = (self.at / "rail.tsv").read_bytes()
        for written, text in (("None.", "None."), ("**None.**", "**None.**"), ("  - n/a", "- n/a"),
                              ("No\nfollow-ups.", "No follow-ups.")):
            self.assertEqual(self.follow_ups_in(f"## Follow-ups\n\n{written}\n").splitlines(), [
                "reports/D1.md lists no follow-ups; nothing added",
                f"not filed, says no work is needed: {text}",
            ])
        self.assertEqual(self.follow_ups_in("# D1 report\n\nStatus: done\n\n## Deviations\n\n- None.\n"),
                         "reports/D1.md has no follow-ups section; nothing added")
        self.assertEqual((self.at / "rail.tsv").read_bytes(), before)

    def test_from_report_reads_every_form_of_the_heading(self):
        self.fired_bug_fix()
        for heading in ("## Follow-ups (outside lease L91)", "### Follow-ups", "## Follow-up",
                        "## Follow-ups outside my lease", "## follow-ups"):
            self.assertEqual(self.follow_ups_in(f"# D1 report\n\n{heading}\n\n- One thing.\n", "--dry-run"),
                             "would add from perf/reports/D1.md#1: One thing.", heading)

    def test_from_report_prints_a_lead_in_above_a_list_and_does_not_file_it(self):
        self.fired_bug_fix()
        self.assertEqual(self.follow_ups_in(LEAD_IN, "--dry-run").splitlines(), [
            "would add from perf/reports/D1.md#1: `pass record` without `--pr` overwrites the item's recorded PR with an "
            "empty value, because `--pr` defaults to `\"\"`.",
            "would add from perf/reports/D1.md#2: `--same-family` is not checked. It writes the `same model family;` note "
            "even when the families differ.",
            "not filed, prose that introduces a list: The explainer found these in `brigade.py`. All are outside L81, "
            "so I did not fix them.",
        ])

    def test_from_report_numbers_the_items_of_two_sections_as_one_list(self):
        self.fired_bug_fix()
        self.assertEqual(self.follow_ups_in(TWO_SECTIONS, "--dry-run").splitlines(), [
            "would add from perf/reports/D1.md#1: `docs/light-mode.md`, in its review-file table, still describes one "
            "`<item>-review.md` file per item.",
            "would add from perf/reports/D1.md#2: The panel sentences in step 7 still say \"handle the send-back below\" "
            "while that bullet sits above them.",
            "would add from perf/reports/D1.md#3: Decide whether `ticket move` should refuse a ticket of an item that owes "
            "its decision.",
        ])

    def test_from_report_dry_run_changes_no_table_and_no_log_and_needs_no_owner(self):
        self.fired_bug_fix()
        self.brigade("set", "--thread", "t1")
        before = self.tables()
        self.assertIn("log.tsv", before)
        self.assertEqual(self.follow_ups_in(BULLETS, "--dry-run", owner=False).splitlines()[2],
                         "would add from perf/reports/D1.md#3: PR #87 was not commented on, approved, or closed.")
        self.assertEqual(self.follow_ups_in(BULLETS, ok=False, owner=False),
                         "brigade: this store is owned by t1@1; pass --owner <thread>@<generation> from status")
        self.assertEqual(self.tables(), before)

    def test_from_report_dry_run_waits_for_a_writer_that_holds_the_store_lock(self):
        self.fired_bug_fix()
        self.review_file("D1.md", BULLETS)
        held = os.open(self.at / "restaurant.lock", os.O_RDWR | os.O_CREAT, 0o644)
        self.addCleanup(os.close, held)
        fcntl.flock(held, fcntl.LOCK_EX)
        dry_run = subprocess.Popen([sys.executable, str(SCRIPT), "--store", str(self.store), "--at", str(self.at),
                                    "ticket", "add", "--from-report", "reports/D1.md", "--dry-run"],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            time.sleep(0.3)
            self.assertIsNone(dry_run.poll())
            fcntl.flock(held, fcntl.LOCK_UN)
            out, err = dry_run.communicate(timeout=10)
        finally:
            dry_run.kill()
        self.assertEqual([line.split(":")[0] for line in out.splitlines()],
                         [f"would add from perf/reports/D1.md#{number}" for number in (1, 2, 3)], err)

    def test_from_report_changes_only_the_ticket_table_the_log_and_last_activity(self):
        self.fired_bug_fix()
        self.review_file("D1.md", BULLETS)

        def changed_by(*command):
            before = self.store_files()
            self.brigade(*command)
            after = self.store_files()
            return before, sorted(name for name in after if after[name] != before.get(name))

        _, by_hand = changed_by("ticket", "add", "--summary", "by hand")
        (self.at / "restaurant.lock").unlink()
        before, from_report = changed_by("ticket", "add", "--from-report", "reports/D1.md")
        self.assertEqual(from_report, ["log.tsv", "rail.tsv", "restaurant.json"])
        self.assertEqual(from_report, by_hand)
        old, new = json.loads(before["restaurant.json"]), json.loads((self.at / "restaurant.json").read_text())
        self.assertEqual([key for key in new if new[key] != old.get(key)], ["lastActivityAt"])

    def test_from_report_skips_text_a_ticket_already_holds_whatever_its_spacing_and_case(self):
        self.fired_bug_fix()
        self.brigade("ticket", "add", "--summary", "pr #87   was NOT commented on, approved, or closed.")
        self.assertEqual(self.follow_ups_in(BULLETS).splitlines()[2],
                         "skipped perf/reports/D1.md#3, same text as T2 (waiting): "
                         "PR #87 was not commented on, approved, or closed.")
        self.assertEqual(self.brigade("ticket", "list").splitlines()[-1].split(" ", 1)[0], "T4")

    def test_from_report_skips_the_second_of_two_items_with_the_same_text(self):
        self.fired_bug_fix()
        twice = "## Follow-ups\n\n- Same thing.\n- same  THING.\n- Other thing.\n"
        self.assertEqual(self.follow_ups_in(twice, "--dry-run").splitlines(), [
            "would add from perf/reports/D1.md#1: Same thing.",
            "skipped perf/reports/D1.md#2, same text as #1 above: same  THING.",
            "would add from perf/reports/D1.md#3: Other thing.",
        ])
        self.assertEqual(self.follow_ups_in(twice).splitlines(), [
            "T2 added from perf/reports/D1.md#1: Same thing.",
            "skipped perf/reports/D1.md#2, same text as T2 (waiting): same  THING.",
            "T3 added from perf/reports/D1.md#3: Other thing.",
        ])

    def test_from_report_drops_a_list_item_with_no_text(self):
        self.fired_bug_fix()
        self.assertEqual(self.follow_ups_in("## Follow-ups\n\n- \n- One thing.\n", "--dry-run"),
                         "would add from perf/reports/D1.md#1: One thing.")

    def test_from_report_takes_the_report_by_name_or_by_a_path_into_this_store(self):
        self.fired_bug_fix()
        path = self.review_file("D1.md", "## Follow-ups\n\n- One thing.\n")
        for spelling in ("D1.md", "reports/D1.md", str(path)):
            self.assertEqual(self.brigade("ticket", "add", "--from-report", spelling, "--dry-run"),
                             "would add from perf/reports/D1.md#1: One thing.", spelling)

    def test_from_report_refuses_what_is_not_an_item_report_of_this_store(self):
        self.fired_bug_fix()
        body = "## Follow-ups\n\n- One thing.\n"
        self.review_file("D1.md", body)
        before = (self.at / "rail.tsv").read_bytes()
        add = ("ticket", "add", "--from-report")
        for name in ("D1-review-1.md", "notes.md", "D1-attempt1.md"):
            self.review_file(name, body)
            self.assertEqual(self.brigade(*add, f"reports/{name}", ok=False),
                             f"brigade: {name} is not an item report; name a file like reports/D2.md")
        elsewhere = Path(self.temporary.name) / "elsewhere" / "D1.md"
        elsewhere.parent.mkdir()
        elsewhere.write_text(body)
        self.assertEqual(self.brigade(*add, str(elsewhere), ok=False),
                         f"brigade: {elsewhere} is outside this store's reports/; name reports/D1.md")
        self.assertEqual(self.brigade(*add, "reports/D7.md", ok=False),
                         "brigade: reports/D7.md does not exist; nothing added")
        self.review_file("D9.md", body)
        self.assertEqual(self.brigade(*add, "reports/D9.md", ok=False), "brigade: no D9 in dishes.tsv")
        (self.at / "reports" / "D1.md").write_bytes(b"## Follow-ups\n\n- caf\xe9\n")
        self.assertEqual(self.brigade(*add, "reports/D1.md", ok=False),
                         "brigade: reports/D1.md is not UTF-8 text; nothing added")
        self.assertEqual((self.at / "rail.tsv").read_bytes(), before)

    def test_from_report_refuses_a_symbolic_link_and_a_file_that_resolves_outside_reports(self):
        self.fired_bug_fix()
        body = "## Follow-ups\n\n- Outside file was read.\n"
        report = self.at / "reports" / "D1.md"
        outside = Path(self.temporary.name) / "outside"
        (outside / "reports").mkdir(parents=True)
        (outside / "D1.md").write_text(body)
        (outside / "reports" / "D1.md").write_text(body)
        notes = self.review_file("notes.md", body)
        before = (self.at / "rail.tsv").read_bytes()
        add = ("ticket", "add", "--from-report")
        for target in (outside / "D1.md", notes):
            report.symlink_to(target)
            for spelling in ("D1.md", "reports/D1.md", str(report)):
                for extra in ((), ("--dry-run",)):
                    self.assertEqual(self.brigade(*add, spelling, *extra, ok=False),
                                     "brigade: reports/D1.md is a symbolic link; nothing added")
            self.assertEqual(self.brigade(*add, str(outside / "D1.md"), "--dry-run", ok=False),
                             f"brigade: {outside / 'D1.md'} is outside this store's reports/; name reports/D1.md")
            report.unlink()
        notes.unlink()
        (self.at / "reports").rmdir()
        (self.at / "reports").symlink_to(outside / "reports")
        for extra in ((), ("--dry-run",)):
            self.assertEqual(self.brigade(*add, "reports/D1.md", *extra, ok=False),
                             "brigade: reports/D1.md resolves outside this store's reports/; nothing added")
        self.assertEqual((self.at / "rail.tsv").read_bytes(), before)

    def test_from_report_refuses_a_path_with_a_dot_dot_component_wherever_it_resolves(self):
        self.fired_bug_fix()
        reports = self.review_file("D1.md", "## Follow-ups\n\n- One thing.\n").parent
        before = (self.at / "rail.tsv").read_bytes()
        for spelling in ("reports/../reports/D1.md", "../D1.md", f"{reports}/../reports/D1.md",
                         f"{reports}/../../../../outside/D1.md", "reports/.."):
            for extra in ((), ("--dry-run",)):
                self.assertEqual(self.brigade("ticket", "add", "--from-report", spelling, *extra, ok=False),
                                 f"brigade: {spelling} has a .. component; name a file like reports/D2.md")
        self.assertEqual((self.at / "rail.tsv").read_bytes(), before)

    def test_from_report_refuses_the_flags_of_a_hand_written_ticket(self):
        self.fired_bug_fix()
        self.review_file("D1.md", "## Follow-ups\n\n- One thing.\n")
        before = (self.at / "rail.tsv").read_bytes()
        add = ("ticket", "add", "--from-report", "reports/D1.md")
        for extra in (("--source", "github"), ("--ref", "x"), ("--request", "A1"), ("--again",)):
            self.assertEqual(self.brigade(*add, *extra, ok=False),
                             "brigade: --from-report takes no --source, --ref, --request, or --again")
        self.assertEqual(self.brigade("ticket", "add", "--summary", "x", "--dry-run", ok=False),
                         "brigade: --dry-run needs --from-report")
        self.assertEqual(self.brigade("ticket", "add", "--summary", "x", "--source", "report", ok=False),
                         "brigade: no coordinator owns intake from report; the one that reads it runs set --intake report")
        for flags, message in ((("--summary", "x", "--from-report", "reports/D1.md"),
                                "argument --from-report: not allowed with argument --summary"),
                               ((), "one of the arguments --summary --from-report is required")):
            result = subprocess.run([sys.executable, str(SCRIPT), "--store", str(self.store), "--at", str(self.at),
                                     "ticket", "add", *flags], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn(message, result.stderr)
        self.assertEqual((self.at / "rail.tsv").read_bytes(), before)

    def test_a_member_send_back_recorded_before_the_passing_rows_changes_no_verdict(self):
        self.fired_bug_fix()
        self.assertEqual(self.brigade("pass", "record", "D1", "--pr", "u/9", "--sha", "abc", "--verdict", "send-back",
                                      "--author", CLAUDE, "--verifier", "grok/grok-4.7", "--note", "nit", "--member"),
                         "D1: member send-back on record; D1 stays in-progress")
        self.assertEqual(self.dish_fields("state", "pr", "sha"), ("in-progress", "", ""))
        self.assertEqual(self.check_json("abc"), (1, "", "brigade: D1 has no review verdict for abc"))
        self.record("abc", "pass")
        self.assertEqual(self.brigade("pass", "check", "D1", "--sha", "abc"), f"D1 at abc passed review by {CODEX}")
        code, out, err = self.check_json("abc")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(json.loads(out), {"verdict": "pass", "author": CLAUDE, "verifier": CODEX, "note": "", "crossFamily": True})
        self.assertEqual([row[4:] for row in self.pass_rows()],
                         [["send-back", CLAUDE, "grok/grok-4.7", "nit", "", "yes"], ["pass", CLAUDE, CODEX, "", "", ""]])

    def test_a_member_send_back_recorded_after_the_passing_rows_changes_no_verdict(self):
        self.fired_bug_fix()
        self.record("abc", "pass")
        self.assertEqual(self.brigade("pass", "record", "D1", "--pr", "u/9", "--sha", "abc", "--verdict", "send-back",
                                      "--author", CLAUDE, "--verifier", "grok/grok-4.7", "--note", "nit", "--member"),
                         "D1: member send-back on record; D1 stays passed")
        self.assertEqual(self.dish_fields("state", "pr", "sha"), ("passed", "", "abc"))
        self.assertEqual(self.brigade("pass", "check", "D1", "--sha", "abc"), f"D1 at abc passed review by {CODEX}")
        code, out, err = self.check_json("abc")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(json.loads(out), {"verdict": "pass", "author": CLAUDE, "verifier": CODEX, "note": "", "crossFamily": True})
        self.assertEqual(self.brigade("dish", "D1", "--state", "queued"), "D1 queued")

    def test_a_member_row_follows_the_family_rule_and_takes_no_late_flag(self):
        self.fired_bug_fix()
        member = ("pass", "record", "D1", "--sha", "abc", "--verdict", "send-back", "--author", CLAUDE, "--member")
        self.assertIn("same model family", self.brigade(*member, "--verifier", "cursor/claude-sonnet-5-5", ok=False))
        self.assertIn("not allowed with argument", self.brigade(*member, "--verifier", CODEX, "--late", ok=False))
        self.assertEqual(self.pass_rows(), [])

    def test_pass_record_for_an_unknown_item_leaves_no_row(self):
        self.fired_bug_fix()
        for flags in ((), ("--member",), ("--late",)):
            self.assertEqual(self.brigade("pass", "record", "D9", "--sha", "abc", "--verdict", "pass",
                                          "--author", CLAUDE, "--verifier", CODEX, *flags, ok=False),
                             "brigade: no D9 in dishes.tsv")
        self.assertEqual(self.pass_rows(), [])

    def close_run(self, *flags):
        result = subprocess.run([sys.executable, str(SCRIPT), "--store", str(self.store), "--at", str(self.at),
                                 *_owner_words(self.at), "close", *flags], capture_output=True, text=True)
        return result.returncode, result.stdout.strip(), result.stderr.strip()

    def no_row(self, name, dish="D1"):
        return (f"brigade: warning: reports/{name} has no review row; record it with pass record {dish} --report {name}, "
                f"and --late when {dish} has moved past that round")

    def aged(self, name, year):
        path = self.review_file(name)
        stamp = datetime(year, 1, 1, tzinfo=timezone.utc).timestamp()
        os.utime(path, (stamp, stamp))
        return path

    def test_close_warns_about_a_review_report_with_no_row_and_still_exits_0(self):
        self.fired_bug_fix()
        code, before, err = self.close_run("--dry-run")
        self.assertEqual((code, err), (0, ""))
        self.review_file("D1-review-2.md")
        self.assertEqual(self.close_run("--dry-run"), (0, before, self.no_row("D1-review-2.md")))
        code, out, err = self.close_run("--to-file")
        self.assertEqual((code, err), (0, self.no_row("D1-review-2.md")))
        self.assertEqual(Path(out).read_text().strip(), before)
        code, out, err = self.close_run()
        self.assertEqual((code, err), (0, self.no_row("D1-review-2.md")))
        self.assertEqual(out.splitlines()[0], "# Perf report")
        self.assertNotIn("warning", out)

    def test_close_does_not_warn_about_a_report_a_row_names(self):
        self.fired_bug_fix()
        self.aged("D1-review-1.md", 2099)
        self.aged("D1-review-1-panel-2.md", 2099)
        self.record("abc", "send-back", "--report", "D1-review-1.md")
        self.record("abc", "pass", "--member", "--report", "D1-review-1-panel-2.md", verifier="grok/grok-4.7")
        self.assertEqual(self.close_run("--dry-run")[2], "")

    def test_close_matches_a_row_that_names_no_report_to_the_reports_written_before_it(self):
        self.fired_bug_fix()
        self.aged("D1-review.md", 2020)
        self.aged("D1-review-bunny.md", 2020)
        self.assertEqual(self.close_run("--dry-run")[2],
                         "\n".join([self.no_row("D1-review-bunny.md"), self.no_row("D1-review.md")]))
        self.record("abc", "send-back")
        self.assertEqual(self.close_run("--dry-run")[2], "")
        self.aged("D1-review-2.md", 2099)
        self.assertEqual(self.close_run("--dry-run")[2], self.no_row("D1-review-2.md"))

    def test_a_row_that_names_a_report_matches_no_other_report(self):
        self.fired_bug_fix()
        self.aged("D1-review-1.md", 2020)
        self.aged("D1-review-2.md", 2020)
        self.aged("D7-review.md", 2020)
        self.record("abc", "send-back", "--report", "D1-review-2.md")
        self.assertEqual(self.close_run("--dry-run")[2],
                         "\n".join([self.no_row("D1-review-1.md"), self.no_row("D7-review.md", "D7")]))

    def test_close_ignores_a_file_that_is_not_a_review_report(self):
        self.fired_bug_fix()
        for name in ("D1.md", "notes.md", "D1-review.txt", "D1-reviewed.md", "xD1-review.md"):
            self.aged(name, 2099)
        self.assertEqual(self.close_run("--dry-run")[2], "")

    def test_report_lists_only_what_changed_since_the_last_report(self):
        self.open()
        self.brigade("ticket", "add", "--summary", "Startup is slow")
        self.brigade("ticket", "add", "--summary", "Splash hangs")
        self.brigade("fire", "--tickets", "T1", "--station", "perf-issue", "--summary", "Cut cold start time")
        self.brigade("86", "add", "--question", "Drop Windows 7 support?", "--options", "yes, no", "--default", "no")
        first = self.brigade("close")
        self.assertIn("## In progress\n\n- D1 (T1): Cut cold start time\n", first)
        self.assertIn("## New tickets, not started\n\n- T2: Splash hangs\n", first)
        self.assertIn("- Q1: Drop Windows 7 support? Options: yes, no. Default if no answer: no.", first)
        self.brigade("pass", "record", "D1", "--pr", "https://github.com/o/r/pull/7", "--sha", "abc", "--verdict", "pass",
                     "--author", CLAUDE, "--verifier", CODEX)
        self.brigade("dish", "D1", "--state", "merged")
        self.brigade("86", "answer", "Q1", "--answer", "no")
        second = self.brigade("close")
        self.assertIn("## Merged\n\n- D1 (T1): Cut cold start time https://github.com/o/r/pull/7", second)
        self.assertNotIn("In progress", second)
        self.assertNotIn("Passed review", second)
        self.assertNotIn("Decisions for you", second)
        self.assertIn("Nothing new.", self.brigade("close"))
        self.assertEqual(len(list((self.at / "closeouts").glob("*.md"))), 3)

    def test_a_dish_that_moves_through_every_state_in_one_report_appears_once(self):
        self.open()
        self.brigade("ticket", "add", "--summary", "s")
        self.brigade("ticket", "add", "--summary", "UI", "--source", "user")
        self.brigade("ticket", "set", "T2", "--state", "dropped")
        self.brigade("fire", "--tickets", "T1", "--station", "bug-fix", "--summary", "Fix s")
        self.brigade("dish", "D1", "--state", "in-review", "--sha", "abc")
        self.brigade("pass", "record", "D1", "--sha", "abc", "--verdict", "pass", "--author", "grok/grok-4.7", "--verifier", CODEX)
        self.brigade("dish", "D1", "--state", "merged")
        self.assertEqual(self.brigade("close"), "\n".join([
            "# Perf report", "",
            f"Since opening. merged: 1.", "",
            "## Merged", "", "- D1 (T1): Fix s", "",
            "## Dropped", "", "- T2: UI",
        ]))

    def test_close_to_file_prints_the_written_path_and_advances_the_report(self):
        self.open()
        self.brigade("ticket", "add", "--summary", "s")
        self.brigade("ticket", "add", "--summary", "UI", "--source", "user")
        self.brigade("ticket", "set", "T2", "--state", "dropped")
        self.brigade("fire", "--tickets", "T1", "--station", "bug-fix", "--summary", "Fix s")
        self.brigade("dish", "D1", "--state", "in-review", "--sha", "abc")
        self.brigade("pass", "record", "D1", "--sha", "abc", "--verdict", "pass", "--author", "grok/grok-4.7", "--verifier", CODEX)
        self.brigade("dish", "D1", "--state", "merged")
        written = self.brigade("close", "--to-file")
        files = list((self.at / "closeouts").glob("*.md"))
        self.assertEqual(len(files), 1)
        self.assertEqual(written, str(files[0].resolve()))
        self.assertIn("## Merged\n\n- D1 (T1): Fix s", files[0].read_text())
        self.assertIn("Nothing new.", self.brigade("close"))

    def test_close_to_file_with_dry_run_writes_no_closeout(self):
        self.open()
        self.brigade("close", "--to-file", "--dry-run", ok=False)
        self.assertEqual(list((self.at / "closeouts").glob("*.md")), [])

    def test_status_help_names_the_thread_line_then_counts(self):
        env = os.environ | {"COLUMNS": "200"}
        result = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("status              the thread line first, then counts, then reports to, mode, and owner when present", result.stdout)
        self.assertNotIn("one line of counts", result.stdout)

    def test_status_and_walk_speak_plain_engineering_prose(self):
        self.open()
        self.brigade("set", "--thread", "thread-1", "--schedule", "report=s-1")
        self.brigade("ticket", "add", "--summary", "s")
        self.brigade("86", "add", "--question", "Ship it?", "--options", "yes, no", "--default", "no")
        self.assertEqual(self.brigade("status"),
                         "thread thread-1\nreporting: milestones, no landing contract, waiting tickets: 1, decisions for you: 1\nowner thread-1@1")
        self.assertEqual(self.brigade("walk"), "\n".join([
            f"{_shown_root(self.project)}: no landing contract",
            "  Perf (reports milestones): waiting tickets: 1, decisions for you: 1",
            "    thread thread-1",
            "    Q1: Ship it?",
        ]))
        self.assertEqual(json.loads((self.at / "restaurant.json").read_text())["schedules"], {"report": "s-1"})
        for word in ("86", "plate", "heard", "chef", "fire", "pass "):
            self.assertNotIn(word, self.brigade("status").lower())

    def test_status_without_a_contract_ignores_a_stored_landing_field(self):
        self.open()
        self.assertNotIn("landing", json.loads((self.at / "restaurant.json").read_text()))
        self.assertEqual(self.brigade("status"), "thread not recorded\nreporting: milestones, no landing contract")
        meta = json.loads((self.at / "restaurant.json").read_text())
        meta["landing"] = "merge"
        (self.at / "restaurant.json").write_text(json.dumps(meta, indent=2) + "\n")
        self.assertEqual(self.brigade("status"), "thread not recorded\nreporting: milestones, no landing contract")
        walked = self.brigade("walk")
        self.assertEqual(walked.splitlines()[0], f"{_shown_root(self.project)}: no landing contract")
        self.assertNotIn("lands by", walked)

    def test_set_landing_exits_2(self):
        self.open()
        before = (self.at / "restaurant.json").read_bytes()
        result = subprocess.run([sys.executable, str(SCRIPT), "--store", str(self.store), "--at", str(self.at),
                                 "set", "--landing", "merge"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual((self.at / "restaurant.json").read_bytes(), before)

    def test_walk_prints_a_home_directory_as_a_tilde(self):
        from unittest import mock
        project = Path.home() / "brigade-no-such-contract-d57"
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": self.land_env()["XDG_STATE_HOME"]}):
            directory = self.store / "brigade-no-such-contract-d57" / "docs"
            self.assertEqual(self.brigade("open", "--project-root", str(project), "--name", "Docs"), f"opened {directory}")
            self.assertEqual(self.brigade("walk"), "\n".join([
                "~/brigade-no-such-contract-d57: no landing contract",
                "  Docs (reports milestones): nothing on record",
                "    thread not recorded",
            ]))

    def test_status_and_walk_follow_a_landing_mode_change(self):
        from unittest import mock
        self.git_project()
        remote = Path(self.temporary.name) / "origin.git"
        subprocess.run(["git", "init", "--bare", "-q", "-b", "main", str(remote)], check=True)
        subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=self.project, check=True)
        subprocess.run(["git", "push", "-q", "origin", "main"], cwd=self.project, check=True)
        self.land("init", "--trunk", "main", "--mode", "human")
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": self.land_env()["XDG_STATE_HOME"]}):
            self.open()
            self.land("mode", "merge")
            self.assertEqual(self.brigade("status"), "thread not recorded\nreporting: milestones, lands by merge")
            header = self.brigade("walk").splitlines()[0]
            self.assertEqual(header, f"{_shown_root(self.project)}: {self.land('status')}")
            self.assertTrue(header.startswith(f"{_shown_root(self.project)}: merge mode onto "))

    def test_walk_groups_repositories_and_repo_selects_one(self):
        from unittest import mock
        other = Path(self.temporary.name) / "other-app"
        other.mkdir()
        self.init_landing("--cap", "4")
        run = lambda *command: subprocess.run(command, cwd=other, capture_output=True, text=True, check=True)
        run("git", "init", "-q", "-b", "main")
        (other / "a.txt").write_text("a\n")
        run("git", "add", "-A")
        run("git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
        self.land_repo(other, "init", "--trunk", "lane", "--mode", "local", "--base", "main", "--cap", "4")
        docs = self.store / "bridge-kit" / "docs"
        engine = self.store / "bridge-kit" / "engine"
        core = self.store / "other-app" / "core"
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": self.land_env()["XDG_STATE_HOME"]}):
            self.assertEqual(self.brigade("walk"), f"no restaurants under {self.store}")
            self.run_at(docs, "open", "--project-root", str(self.project), "--name", "Docs")
            self.run_at(engine, "open", "--project-root", str(self.project), "--name", "Engine")
            self.run_at(core, "open", "--project-root", str(other), "--name", "Core")
            self.run_at(docs, "set", "--thread", "thread-docs")
            self.run_at(engine, "set", "--thread", "thread-engine")
            self.run_at(core, "set", "--thread", "thread-core")
            self.run_at(docs, "ticket", "add", "--summary", "Write the guide")
            self.assertEqual(self.run_at(docs, "fire", "--tickets", "T1", "--station", "bug-fix",
                                         "--summary", "Write the guide", "--paths", "a.txt"),
                             "D1 (lease L1 held by docs/D1)")
            self.run_at(engine, "ticket", "add", "--summary", "Blocked edit")
            refused = self.run_at(engine, "fire", "--tickets", "T1", "--station", "bug-fix",
                                  "--summary", "Blocked edit", "--paths", "a.txt", ok=False)
            self.assertIn("nothing fired: paths overlap L1 held by docs/D1", refused)
            self.assertEqual(self.land("lease", "claim", "--holder", "engine/D12", "--paths", "src"), "L2")
            self.assertEqual(self.land("lease", "claim", "--holder", "engine/D13", "--paths", "lib"), "L3")
            self.assertEqual(self.run_at(docs, "86", "add", "--question", "Ship the guide?",
                                         "--options", "yes, no", "--default", "no"), "Q1")
            app = _shown_root(self.project)
            other_root = _shown_root(other)
            expected = "\n".join([
                f"{app}: local mode onto refs/landing/lane. leases held: 3, changes in flight: 3 of 4.",
                "  Docs (reports milestones): in progress: 1, decisions for you: 1",
                "    thread thread-docs, leases L1 (D1)",
                "    Q1: Ship the guide?",
                "  Engine (reports milestones): waiting tickets: 1 (1 blocked)",
                "    thread thread-engine, leases L2 (D12), L3 (D13)",
                f"{other_root}: local mode onto refs/landing/lane. changes in flight: 0 of 4.",
                "  Core (reports milestones): nothing on record",
                "    thread thread-core",
            ])
            self.assertEqual(self.brigade("walk"), expected)
            self.assertEqual(self.brigade("walk", "--repo", str(self.project)), "\n".join(expected.splitlines()[:6]))
            self.assertEqual(self.brigade("walk", "--repo", str(other)), "\n".join(expected.splitlines()[6:]))
            missing = Path(self.temporary.name) / "empty-repo"
            missing.mkdir()
            self.assertEqual(self.brigade("walk", "--repo", str(missing)), f"no restaurants for {missing.resolve()}")

    def fire_one(self, station="perf-issue", timebox="60"):
        (self.at / "menu.md").write_text("# Menu: Perf\n\n## Purpose\n\nMake startup fast.\n\n## Budget\n\nsmall\n")
        self.brigade("ticket", "add", "--summary", "Startup is slow")
        return self.brigade("fire", "--tickets", "T1", "--station", station, "--summary", "Cut startup", "--branch", "perf/d1",
                            "--thread", "thread-9", "--timebox", timebox)

    def test_a_state_is_logged_only_when_it_changes(self):
        self.open()
        self.fire_one()
        self.brigade("dish", "D1", "--state", "in-progress", "--task", "t-1")
        self.brigade("pass", "record", "D1", "--sha", "abc", "--verdict", "pass", "--author", "grok/grok-4.7", "--verifier", CODEX)
        self.brigade("dish", "D1", "--state", "merged")
        self.brigade("ticket", "set", "T1", "--state", "done")
        log = (self.at / "log.tsv").read_text()
        self.assertEqual(log.count("\tdish\tD1\tin-progress\t"), 1)
        self.assertEqual(log.count("\tticket\tT1\tdone\t"), 1)

    def test_brief_assembles_every_field_and_adds_the_exclusive_rule_for_measuring_stations(self):
        self.open()
        self.fire_one()
        self.brigade("set", "--thread", "thread-coord")
        text = self.brigade("brief", "D1", "--goal", "Cold start under 400 ms.", "--acceptance", "Median cold start below 400 ms",
                            "--verify", "npm run perf", "--paths", "src/boot.ts", "--lease", "L4", "--base", "origin/main")
        self.assertTrue(text.startswith("Use the poteto-mode skill and its `perf-issue` playbook."))
        report = f"{self.at}/reports/D1.md"
        for part in ("PURPOSE: Make startup fast.", "TICKETS: T1: Startup is slow", "branch `perf/d1`, started from `origin/main`",
                     "leased to you as L4: src/boot.ts", "- Median cold start below 400 ms", "slot --exclusive --",
                     "TIMEBOX: 60 minutes. The timebox orders the work and never waives a playbook step (How, Architect, investigation, or the implementation delegate). At the limit, write the report with what remains instead of skipping steps.",
                     f"Write it to {report}", "1. Write in plain engineering prose.",
                     f'call t3_thread_send to thread thread-coord with mode "auto" and the one-line message "D1 done: report at {report}".'):
            self.assertIn(part, text)
        self.assertEqual((self.at / "briefs/D1.md").read_text().strip(), text)

    def test_a_report_that_follows_the_brief_is_read_by_ticket_add_from_report(self):
        self.open()
        self.fire_one()
        self.brigade("set", "--thread", "thread-coord")
        text = self.brigade("brief", "D1", "--goal", "g", "--acceptance", "a", "--verify", "v", "--paths", "src/boot.ts",
                            "--lease", "L4", "--base", "origin/main")
        line = next(line for line in text.splitlines() if line.startswith("- Write it to "))
        asked = "List each follow-up as one top-level list item under a `"
        heading = line.split(asked, 1)[1].split("`", 1)[0]
        self.assertTrue(line.endswith(f"{asked}{heading}` heading, or write `None.` there."), line)
        self.review_file("D1.md", f"# D1\n\nStatus: done\n\n{heading}\n\n- Warm start is still slow.\n")
        self.assertEqual(self.brigade("ticket", "add", "--from-report", "reports/D1.md"),
                         "T2 added from perf/reports/D1.md#1: Warm start is still slow.")
        self.review_file("D1.md", f"# D1\n\nStatus: done\n\n{heading}\n\nNone.\n")
        self.assertEqual(self.brigade("ticket", "add", "--from-report", "reports/D1.md"),
                         "reports/D1.md lists no follow-ups; nothing added\nnot filed, says no work is needed: None.")

    def test_brief_refuses_when_no_coordinator_thread_is_recorded(self):
        self.open()
        self.fire_one(station="bug-fix")
        error = self.brigade("brief", "D1", "--goal", "g", "--acceptance", "a", "--verify", "v",
                             "--paths", "a", "--lease", "L1", "--base", "origin/main", ok=False)
        self.assertIn("brigade.py set --thread", error)
        self.assertFalse((self.at / "briefs" / "D1.md").exists())

    def test_brief_refuses_a_menu_without_a_purpose_or_a_missing_acceptance(self):
        self.open()
        self.brigade("ticket", "add", "--summary", "s")
        self.brigade("fire", "--tickets", "T1", "--station", "bug-fix", "--summary", "Fix s")
        self.brigade("set", "--thread", "thread-coord")
        args = ["brief", "D1", "--goal", "g", "--verify", "v", "--paths", "a", "--lease", "L1", "--base", "origin/main"]
        self.assertIn("menu.md has no purpose yet", self.brigade(*args, "--acceptance", "a", ok=False))
        (self.at / "menu.md").write_text("## Purpose\n\nFix bugs.\n")
        self.assertIn("at least one --acceptance", self.brigade(*args, ok=False))
        self.assertNotIn("slot --exclusive", self.brigade(*args, "--acceptance", "a"))

    def test_watch_reports_running_finished_and_overdue_work(self):
        self.open()
        self.assertEqual(self.brigade("watch"), "no work in progress")
        self.fire_one(timebox="30")
        self.assertEqual(self.brigade("watch"), "D1: running 0m of 30m (thread thread-9)")
        log = self.at / "log.tsv"
        log.write_text(log.read_text().replace(f"{__import__('datetime').date.today().year}-", "2020-"))
        self.assertIn("D1: over its 30m timebox", self.brigade("watch"))
        (self.at / "reports").mkdir()
        (self.at / "reports/D1.md").write_text("done")
        self.assertEqual(self.brigade("watch"), "D1: report written, no report-back (thread thread-9)")
        self.assertEqual(self.brigade("dish", "D1", "--reported"), "D1 in-progress")
        self.assertEqual(self.brigade("watch"), "D1: report written 0m ago; review it even if the worker's run is still open (thread thread-9)")
        self.brigade("dish", "D1", "--state", "sent-back")
        self.brigade("dish", "D1", "--state", "in-progress")
        self.assertEqual(self.brigade("watch"), "D1: in progress with no worker thread; launch a fresh worker")
        self.brigade("dish", "D1", "--thread", "thread-10")
        (self.at / "reports/D1.md").write_text("second attempt")
        self.assertEqual(self.brigade("watch"), "D1: report written, no report-back (thread thread-10)")

    def test_a_send_back_clears_the_worker_and_refuses_the_old_thread(self):
        self.open()
        self.fire_one()
        self.brigade("dish", "D1", "--state", "sent-back")
        self.assertEqual(self.brigade("dish", "D1", "--thread", "thread-8"), "D1 sent-back")
        self.assertEqual(self.brigade("dish", "D1", "--thread", "thread-9", ok=False),
                         "brigade: thread thread-9 is an earlier attempt of D1; a send-back launches a fresh worker")
        self.assertEqual(self.table_row(self.at, "dishes.tsv", "D1")["thread"], "thread-8")
        refused = self.brigade("dish", "D1", "--state", "in-progress", "--thread", "thread-9", ok=False)
        self.assertEqual(refused, "brigade: thread thread-9 is an earlier attempt of D1; a send-back launches a fresh worker")
        self.assertEqual(self.table_row(self.at, "dishes.tsv", "D1")["state"], "sent-back")
        self.assertEqual(self.table_row(self.at, "dishes.tsv", "D1")["thread"], "thread-8")
        self.assertEqual(self.brigade("dish", "D1", "--state", "in-progress", "--thread", "thread-10"), "D1 in-progress")
        self.assertEqual(self.table_row(self.at, "dishes.tsv", "D1")["thread"], "thread-10")
        self.brigade("dish", "D1", "--state", "sent-back")
        self.assertEqual(self.brigade("dish", "D1", "--state", "in-progress"), "D1 in-progress")
        self.assertEqual(self.table_row(self.at, "dishes.tsv", "D1")["thread"], "")
        self.assertEqual(self.brigade("watch"), "D1: in progress with no worker thread; launch a fresh worker")
        self.assertEqual(self.brigade("dish", "D1", "--thread", "thread-9", ok=False),
                         "brigade: thread thread-9 is an earlier attempt of D1; a send-back launches a fresh worker")
        self.assertEqual(self.brigade("dish", "D1", "--thread", "thread-10", ok=False),
                         "brigade: thread thread-10 is an earlier attempt of D1; a send-back launches a fresh worker")
        self.assertEqual(self.table_row(self.at, "dishes.tsv", "D1")["thread"], "")
        self.assertEqual(self.brigade("dish", "D1", "--thread", "thread-11"), "D1 in-progress")
        self.assertEqual(self.brigade("dish", "D1", "--thread", "thread-11"), "D1 in-progress")

    def test_replacing_an_in_progress_worker_starts_a_new_attempt(self):
        self.open()
        self.fire_one(timebox="60")
        log = self.at / "log.tsv"
        log.write_text(log.read_text().replace(f"{__import__('datetime').date.today().year}-", "2020-"))
        report = self.at / "reports" / "D1.md"
        report.parent.mkdir()
        report.write_text("partial from the overdue worker")
        self.assertEqual(self.brigade("watch"), "D1: report written, no report-back (thread thread-9)")
        self.assertEqual(self.brigade("dish", "D1", "--state", "in-progress", "--thread", "fresh-worker"), "D1 in-progress")
        self.assertEqual(self.brigade("watch"), "D1: running 0m of 60m (thread fresh-worker)")
        report.write_text("partial from the fresh worker")
        self.assertEqual(self.brigade("watch"), "D1: report written, no report-back (thread fresh-worker)")
        self.brigade("dish", "D1", "--timebox", "90", "--task", "t-2")
        self.assertEqual(self.brigade("watch"), "D1: report written, no report-back (thread fresh-worker)")
        self.brigade("dish", "D1", "--state", "in-progress", "--thread", "fresh-worker")
        self.assertEqual(self.brigade("watch"), "D1: report written, no report-back (thread fresh-worker)")
        self.brigade("dish", "D1", "--reported")
        self.assertEqual(self.brigade("watch"), "D1: report written 0m ago; review it even if the worker's run is still open (thread fresh-worker)")
        self.brigade("dish", "D1", "--thread", "worker-3")
        self.assertEqual(self.brigade("watch"), "D1: running 0m of 90m (thread worker-3)")
        self.assertEqual(self.brigade("dish", "D1", "--thread", "thread-9", ok=False),
                         "brigade: thread thread-9 is an earlier attempt of D1; a send-back launches a fresh worker")
        self.assertEqual(self.table_row(self.at, "dishes.tsv", "D1")["thread"], "worker-3")
        report.write_text("partial from worker-3")
        self.assertEqual(self.brigade("watch"), "D1: report written, no report-back (thread worker-3)")

    def test_an_idle_replacement_with_an_earlier_report_reaches_the_nudge(self):
        self.open()
        self.fire_one(timebox="60")
        log = self.at / "log.tsv"
        log.write_text(log.read_text().replace(f"{__import__('datetime').date.today().year}-", "2020-"))
        report = self.at / "reports" / "D1.md"
        report.parent.mkdir()
        report.write_text("report from the replaced worker")
        self.brigade("dish", "D1", "--state", "in-progress", "--thread", "fresh-worker")
        line = self.brigade("watch")
        text = (ROOT / "t3/added/brigade/SKILL.md").read_text()
        section = text.split("## Liveness check", 1)[1].split("\n## ", 1)[0]
        step = next(row for row in section.splitlines() if row.startswith("5. "))
        trigger = step.split("`", 2)[1].split("Nm")[0].replace("D<n>", "D1")
        self.assertEqual((report.exists(), line), (True, "D1: running 0m of 60m (thread fresh-worker)"))
        self.assertTrue(line.startswith(trigger), (trigger, line))
        self.assertIn("no report for the current attempt", step)
        self.assertNotIn("no report file exists", step)

    def test_fire_claims_the_lease_and_a_refused_claim_fires_nothing(self):
        import os
        from unittest import mock
        run = lambda *a: subprocess.run(a, cwd=self.project, capture_output=True, text=True, check=True)
        run("git", "init", "-q", "-b", "main")
        (self.project / "a.txt").write_text("a\n")
        run("git", "add", "-A")
        run("git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
        land = ROOT / "t3/added/landing/scripts/land.py"
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(Path(self.temporary.name) / "state")}):
            subprocess.run([sys.executable, str(land), "--repo", str(self.project), "init", "--trunk", "lane", "--mode", "local", "--base", "main"],
                           check=True, capture_output=True)
            self.open()
            (self.at / "menu.md").write_text("## Purpose\n\nFast.\n")
            self.brigade("ticket", "add", "--summary", "one")
            self.brigade("ticket", "add", "--summary", "two")
            self.assertEqual(self.brigade("fire", "--tickets", "T1", "--station", "bug-fix", "--summary", "s", "--paths", "src"),
                             "D1 (lease L1 held by perf/D1)")
            self.assertIn("nothing fired: paths overlap L1 held by perf/D1",
                          self.brigade("fire", "--tickets", "T2", "--station", "bug-fix", "--summary", "s", "--paths", "src/x.py", ok=False))
            self.assertEqual(self.brigade("ticket", "list", "--state", "waiting"), "T2 waiting [user] two blocked: lease")
            self.brigade("set", "--thread", "thread-coord")
            text = self.brigade("brief", "D1", "--goal", "g", "--acceptance", "a", "--verify", "v", "--base", "refs/landing/lane")
            self.assertIn("leased to you as L1: src,changes/perf%2Fd1.md.", text)
            self.assertIn("branch `perf/d1`", text)

    def test_fire_claims_outside_the_store_lock_and_rechecks_before_it_writes(self):
        case = Path(self.temporary.name)
        calls = case / "land-calls"
        (case / "land.py").write_text(
            "import sys, time\nfrom pathlib import Path\n"
            f"case = Path({str(case)!r})\n"
            "with open(case / 'land-calls', 'a') as f:\n    f.write(' '.join(sys.argv[3:]) + '\\n')\n"
            "if sys.argv[4] == 'claim':\n"
            "    (case / 'claiming').touch()\n"
            "    end = time.monotonic() + 30\n"
            "    while not (case / 'claim-proceed').exists() and time.monotonic() < end:\n        time.sleep(0.01)\n"
            "    print('L7')\n"
            "else:\n    print('L7 released')\n")
        self.open()
        (self.at / "menu.md").write_text("## Purpose\n\nFast.\n")
        self.brigade("ticket", "add", "--summary", "one")
        firing = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--race-child", "fake-land", str(case),
                                   "--store", str(self.store), "--at", str(self.at),
                                   "fire", "--tickets", "T1", "--station", "bug-fix", "--summary", "s", "--paths", "src"],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                  env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        try:
            _wait_for_path(case / "claiming")
            other = subprocess.run([sys.executable, str(SCRIPT), "--store", str(self.store), "--at", str(self.at),
                                    "fire", "--tickets", "T1", "--station", "bug-fix", "--summary", "other"],
                                   capture_output=True, text=True, timeout=10)
            self.assertEqual(other.stdout.strip(), "D1", other.stderr)
            (case / "claim-proceed").touch()
            _, err = firing.communicate(timeout=10)
        finally:
            firing.kill()
        self.assertEqual(firing.returncode, 1)
        self.assertEqual(err.strip(), "brigade: nothing fired: T1 is assigned, not waiting")
        self.assertEqual(calls.read_text().splitlines(),
                         ["lease claim --holder perf/D1 --paths src,changes/perf%2Fd1.md", "lease release L7"])
        self.assertEqual(self.brigade("status"), "thread not recorded\nreporting: milestones, no landing contract, in progress: 1")

    def test_tabs_and_newlines_in_input_cannot_break_a_table(self):
        self.open()
        self.brigade("ticket", "add", "--summary", "line one\nline\ttwo")
        self.assertEqual(self.brigade("ticket", "list"), "T1 waiting [user] line one line two")

    def test_commands_outside_a_restaurant_fail_with_the_fix(self):
        self.assertIn("run brigade.py open", self.brigade("status", ok=False))

    def test_set_schedule_drops_a_recorded_name_and_a_missing_one(self):
        self.open()
        self.brigade("set", "--schedule", "liveness=sched-4", "--schedule", "drain=sched-5")
        self.brigade("set", "--schedule", "liveness=")
        self.assertEqual(json.loads((self.at / "restaurant.json").read_text())["schedules"], {"drain": "sched-5"})
        self.brigade("set", "--schedule", "evening=")
        self.assertEqual(json.loads((self.at / "restaurant.json").read_text())["schedules"], {"drain": "sched-5"})
        self.brigade("set", "--schedule", "morning=sched-1")
        self.assertEqual(json.loads((self.at / "restaurant.json").read_text())["schedules"],
                         {"drain": "sched-5", "morning": "sched-1"})
        error = self.brigade("set", "--schedule", "drain", ok=False)
        self.assertIn("NAME=ID", error)
        self.assertEqual(json.loads((self.at / "restaurant.json").read_text())["schedules"],
                         {"drain": "sched-5", "morning": "sched-1"})

    def test_open_records_reporting_and_defaults_to_milestones(self):
        self.open()
        meta = json.loads((self.at / "restaurant.json").read_text())
        self.assertEqual(meta["reporting"], "milestones")
        self.assertNotIn("landing", meta)
        self.assertEqual(self.brigade("status"), "thread not recorded\nreporting: milestones, no landing contract")
        self.assertIn("reports milestones", self.brigade("walk"))
        self.assertEqual(self.brigade("open", "--project-root", str(self.project), "--name", "Perf",
                                      "--reporting", "every-turn"), f"exists {self.at}")
        self.assertEqual(json.loads((self.at / "restaurant.json").read_text())["reporting"], "milestones")
        other = self.brigade("open", "--project-root", str(self.project), "--name", "Quiet",
                             "--reporting", "digest")
        quiet = self.store / "bridge-kit" / "quiet"
        self.assertEqual(other, "\n".join([
            f"opened {quiet}",
            f"sibling Perf ({self.at}), thread not recorded",
            "  purpose: not written yet",
            "  off the menu: not written yet",
        ]))
        self.assertEqual(json.loads((quiet / "restaurant.json").read_text())["reporting"], "digest")
        self.assertIn("reports digest", self.brigade("walk"))

    def test_set_reporting_changes_the_level_and_rejects_an_unknown_one(self):
        self.open()
        self.brigade("set", "--reporting", "every-turn")
        self.assertEqual(json.loads((self.at / "restaurant.json").read_text())["reporting"], "every-turn")
        self.assertEqual(self.brigade("status"), "thread not recorded\nreporting: every-turn, no landing contract")
        self.brigade("set", "--reporting", "digest")
        before = (self.at / "restaurant.json").read_text()
        error = self.brigade("set", "--reporting", "hourly", ok=False)
        for level in ("every-turn", "milestones", "digest"):
            self.assertIn(level, error)
        self.assertEqual((self.at / "restaurant.json").read_text(), before)
        opened = self.brigade("open", "--project-root", str(self.project), "--name", "Loud",
                              "--reporting", "hourly", ok=False)
        for level in ("every-turn", "milestones", "digest"):
            self.assertIn(level, opened)
        self.assertFalse((self.store / "bridge-kit" / "loud").exists())

    def literal_brief_fields(self):
        return {
            "goal": "Run `$B status` and `$B close` before $(touch sentinel).",
            "acceptance": ["Median cold start below 400 ms"],
            "verify": "npm run perf",
            "paths": "src/boot.ts",
            "lease": "L4",
            "base": "origin/main",
            "context": ["notes/startup.md"],
        }

    def brief_from_flags(self, fields):
        return self.brigade("brief", "D1", "--goal", fields["goal"], "--acceptance", fields["acceptance"][0],
                            "--verify", fields["verify"], "--paths", fields["paths"], "--lease", fields["lease"],
                            "--base", fields["base"], "--context", fields["context"][0])

    def test_brief_fields_file_matches_flags_and_keeps_shell_text_literal(self):
        self.open()
        self.fire_one()
        self.brigade("set", "--thread", "thread-coord")
        fields = self.literal_brief_fields()
        flagged = self.brief_from_flags(fields)
        path = self.at / "brief-fields.json"
        path.write_text(json.dumps(fields), encoding="utf-8")
        filed = self.brigade("brief", "D1", "--fields", str(path))
        self.assertEqual(filed, flagged)
        goal = fields["goal"]
        self.assertIn(goal, filed)
        for part in ("`", "$B status", "$B close", "$(touch sentinel)"):
            self.assertIn(part, filed)
        self.assertIsNone(json.loads((self.at / "restaurant.json").read_text())["lastReportAt"])
        self.assertEqual(list((self.at / "closeouts").glob("*")), [])

    def test_brief_fields_stdin_matches_the_file(self):
        self.open()
        self.fire_one()
        self.brigade("set", "--thread", "thread-coord")
        fields = self.literal_brief_fields()
        raw = json.dumps(fields)
        path = self.at / "brief-fields.json"
        path.write_text(raw, encoding="utf-8")
        filed = self.brigade("brief", "D1", "--fields", str(path))
        piped = self.brigade("brief", "D1", "--fields", "-", stdin=raw)
        self.assertEqual(piped, filed)
        self.assertIn("$(touch sentinel)", piped)

    def test_a_brief_waiting_on_stdin_leaves_the_store_to_other_commands(self):
        self.open()
        self.fire_one()
        self.brigade("set", "--thread", "thread-coord")
        waiting = subprocess.Popen([sys.executable, str(SCRIPT), "--store", str(self.store), "--at", str(self.at),
                                    *_owner_words(self.at),
                                    "brief", "D1", "--fields", "-"],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            time.sleep(0.3)
            self.assertIsNone(waiting.poll())
            others = [subprocess.Popen([sys.executable, str(SCRIPT), "--store", str(self.store), "--at", str(self.at),
                                        *_owner_words(self.at), *args],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                      for args in (("status",), ("watch",), ("ticket", "add", "--summary", "second"))]
            outputs = [other.communicate(timeout=10) for other in others]
            self.assertEqual([other.returncode for other in others], [0, 0, 0], outputs)
            self.assertEqual(outputs[2][0].strip(), "T2")
            out, err = waiting.communicate(json.dumps(self.literal_brief_fields()), timeout=10)
        finally:
            waiting.kill()
        self.assertEqual(waiting.returncode, 0, err)
        self.assertIn("TICKETS: T1: Startup is slow", out)

    def test_a_shell_reads_brief_fields_without_running_them(self):
        self.open()
        self.fire_one()
        self.brigade("set", "--thread", "thread-coord")
        fields = self.literal_brief_fields()
        flagged = self.brief_from_flags(fields)
        work = Path(self.temporary.name) / "shell"
        work.mkdir()
        script = (
            f"FIELDS='{work / 'fields.json'}'\n"
            f"B='{sys.executable} {SCRIPT} --store {self.store} --at {self.at} {' '.join(_owner_words(self.at))}'\n"
            "cat > \"$FIELDS\" <<'JSON'\n"
            + json.dumps(fields) + "\n"
            "JSON\n"
            "$B brief D1 --fields \"$FIELDS\"\n"
        )
        result = subprocess.run(["bash", "-c", script], cwd=work, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), flagged)
        self.assertFalse((work / "sentinel").exists())
        self.assertIsNone(json.loads((self.at / "restaurant.json").read_text())["lastReportAt"])

    def test_brief_fields_rejects_a_mix_and_bad_json(self):
        self.open()
        self.fire_one()
        self.brigade("set", "--thread", "thread-coord")
        brief = self.at / "briefs" / "D1.md"
        fields = self.at / "brief-fields.json"
        error = self.brigade("brief", "D1", "--fields", str(fields), "--goal", "g", ok=False)
        self.assertIn("use either --fields or the field flags, not both", error)
        self.assertFalse(brief.exists())
        missing = self.at / "no-such-fields.json"
        error = self.brigade("brief", "D1", "--fields", str(missing), ok=False)
        self.assertIn("brief fields:", error)
        self.assertIn("no-such-fields.json", error)
        self.assertFalse(brief.exists())
        fields.write_text("[]\n", encoding="utf-8")
        error = self.brigade("brief", "D1", "--fields", str(fields), ok=False)
        self.assertIn("JSON must be an object", error)
        self.assertFalse(brief.exists())
        fields.write_text(json.dumps({"goal": "g", "acceptance": ["a"], "verify": "v", "base": "main", "nope": "x"}),
                          encoding="utf-8")
        error = self.brigade("brief", "D1", "--fields", str(fields), ok=False)
        self.assertIn("unknown key nope", error)
        self.assertFalse(brief.exists())
        fields.write_text(json.dumps({"goal": "g", "acceptance": "a", "verify": "v", "base": "main"}), encoding="utf-8")
        error = self.brigade("brief", "D1", "--fields", str(fields), ok=False)
        self.assertIn("acceptance must be a list of strings", error)
        self.assertFalse(brief.exists())

    def test_a_restaurant_file_without_reporting_reads_as_milestones(self):
        self.open()
        meta = json.loads((self.at / "restaurant.json").read_text())
        del meta["reporting"]
        (self.at / "restaurant.json").write_text(json.dumps(meta, indent=2) + "\n")
        self.assertNotIn("reporting", json.loads((self.at / "restaurant.json").read_text()))
        self.assertEqual(self.brigade("status"), "thread not recorded\nreporting: milestones, no landing contract")
        self.assertIn("reports milestones", self.brigade("walk"))
        self.assertNotIn("reporting", json.loads((self.at / "restaurant.json").read_text()))

    def log_rows(self):
        lines = (self.at / "log.tsv").read_text().splitlines()
        header = lines[0].split("\t")
        return [dict(zip(header, line.split("\t"))) for line in lines[1:] if line]

    def test_watch_flags_a_reported_run_still_open_past_ten_minutes(self):
        self.open()
        self.fire_one()
        report = self.at / "reports" / "D1.md"
        report.parent.mkdir()
        report.write_text("done")
        self.brigade("dish", "D1", "--reported")
        self.assertEqual(self.brigade("watch"),
                         "D1: report written 0m ago; review it even if the worker's run is still open (thread thread-9)")
        start = (datetime.now(timezone.utc) - timedelta(minutes=60)).isoformat(timespec="microseconds")
        log = self.at / "log.tsv"
        lines = log.read_text().splitlines()
        rewritten = [lines[0]]
        for line in lines[1:]:
            fields = line.split("\t")
            if fields[1:4] == ["dish", "D1", "in-progress"]:
                fields[0] = start
                line = "\t".join(fields)
            rewritten.append(line)
        log.write_text("\n".join(rewritten) + "\n")
        moment = datetime.now(timezone.utc) - timedelta(minutes=12, seconds=30)
        os.utime(report, (moment.timestamp(), moment.timestamp()))
        self.assertEqual(self.brigade("watch"), "D1: reported 12m ago, not in review; read the thread (thread thread-9)")
        moment = datetime.now(timezone.utc) - timedelta(minutes=10, seconds=10)
        os.utime(report, (moment.timestamp(), moment.timestamp()))
        self.assertEqual(self.brigade("watch"),
                         "D1: report written 10m ago; review it even if the worker's run is still open (thread thread-9)")

    def test_hang_records_one_open_run_per_attempt(self):
        self.open()
        self.fire_one()
        error = self.brigade("hang", "D1", "--provider", "grok/grok-4.7", "--minutes", "20", ok=False)
        self.assertIn("no report-back on this attempt", error)
        self.assertEqual([row for row in self.log_rows() if row["kind"] == "hang"], [])
        report = self.at / "reports" / "D1.md"
        report.parent.mkdir()
        report.write_text("done")
        self.brigade("dish", "D1", "--reported")
        self.assertEqual(self.brigade("hang", "D1", "--provider", "grok/grok-4.7", "--minutes", "20"),
                         "D1: grok/grok-4.7 open 20m")
        hangs = [row for row in self.log_rows() if row["kind"] == "hang"]
        self.assertEqual([(row["kind"], row["id"], row["state"], row["note"]) for row in hangs],
                         [("hang", "D1", "open", "grok/grok-4.7 20m")])
        self.assertEqual(self.brigade("hang", "D1", "--provider", "grok/grok-4.7", "--minutes", "5"),
                         "D1: hang already recorded")
        self.assertEqual(len([row for row in self.log_rows() if row["kind"] == "hang"]), 1)
        closed = self.brigade("close", "--dry-run")
        self.assertIn("Cut startup", closed)
        self.assertNotIn("grok/grok-4.7 20m", closed)
        self.brigade("dish", "D1", "--thread", "worker-3")
        error = self.brigade("hang", "D1", "--provider", "grok/grok-4.7", "--minutes", "20", ok=False)
        self.assertIn("no report-back", error)
        report.write_text("done again")
        self.brigade("dish", "D1", "--reported")
        self.brigade("hang", "D1", "--provider", "grok/grok-4.7", "--minutes", "20")
        self.assertEqual(len([row for row in self.log_rows() if row["kind"] == "hang"]), 2)

    def test_hang_records_a_run_left_open_by_an_earlier_attempt(self):
        self.open()
        self.fire_one()
        report = self.at / "reports" / "D1.md"
        report.parent.mkdir()
        report.write_text("done")
        self.brigade("dish", "D1", "--reported")
        self.brigade("dish", "D1", "--thread", "worker-3")
        error = self.brigade("hang", "D1", "--provider", "grok", "--minutes", "13", ok=False)
        self.assertEqual(error, "brigade: no report-back on this attempt; "
                                "for a run left open by an earlier attempt, pass --attempt 1")
        self.assertEqual(self.brigade("hang", "D1", "--attempt", "1", "--provider", "grok", "--minutes", "13"),
                         "D1: grok open 13m (attempt 1)")
        self.assertEqual(self.brigade("hang", "D1", "--attempt", "1", "--provider", "grok", "--minutes", "14"),
                         "D1: hang already recorded")
        self.assertEqual(self.brigade("hang", "D1", "--attempt", "3", "--provider", "grok", "--minutes", "1", ok=False),
                         "brigade: D1 has attempts 1 to 2")
        report.write_text("done again")
        self.brigade("dish", "D1", "--reported")
        self.assertEqual(self.brigade("hang", "D1", "--provider", "grok", "--minutes", "2"), "D1: grok open 2m")
        self.assertEqual(self.brigade("hang", "D1", "--attempt", "2", "--provider", "grok", "--minutes", "2"),
                         "D1: hang already recorded")
        self.assertEqual([row["note"] for row in self.log_rows() if row["kind"] == "hang"],
                         ["grok 13m (attempt 1)", "grok 2m"])

    def test_hang_without_attempt_counts_toward_the_attempt_it_was_recorded_in(self):
        self.open()
        self.fire_one()
        report = self.at / "reports" / "D1.md"
        report.parent.mkdir()
        report.write_text("done")
        self.brigade("dish", "D1", "--reported")
        self.brigade("hang", "D1", "--provider", "grok", "--minutes", "20")
        self.brigade("dish", "D1", "--thread", "worker-3")
        self.assertEqual(self.brigade("hang", "D1", "--attempt", "1", "--provider", "grok", "--minutes", "20"),
                         "D1: hang already recorded")

    def test_dropping_an_item_returns_its_tickets_to_waiting(self):
        from unittest import mock
        self.init_landing()
        ref = "https://github.com/o/r/issues/1"
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": self.land_env()["XDG_STATE_HOME"]}):
            self.open()
            self.brigade("set", "--intake", "github")
            self.assertEqual(self.brigade("ticket", "add", "--summary", "bug", "--source", "github", "--ref", ref), "T1")
            self.assertEqual(self.brigade("fire", "--tickets", "T1", "--station", "bug-fix", "--summary", "fix",
                                          "--paths", "a.py"), "D1 (lease L1 held by perf/D1)")
            self.assertEqual(self.brigade("dish", "D1", "--state", "dropped"), "D1 dropped; T1 waiting again")
            self.assertEqual(self.brigade("ticket", "list"), f"T1 waiting [github] bug {ref}")
            self.assertEqual(self.table_row(self.at, "rail.tsv", "T1")["dish"], "")
            self.assertEqual([(row["kind"], row["id"], row["state"], row["note"]) for row in self.log_rows()][-2:],
                             [("dish", "D1", "dropped", "fix (released L1)"),
                              ("ticket", "T1", "waiting", "bug (back from dropped D1)")])
            self.assertIn("waiting tickets: 1", self.brigade("status"))
            self.assertEqual(self.brigade("ticket", "add", "--summary", "bug again", "--source", "github", "--ref", ref,
                                          ok=False), f"brigade: {ref} is already T1 (waiting); nothing added")
            self.assertEqual(self.brigade("fire", "--tickets", "T1", "--station", "bug-fix", "--summary", "fix",
                                          "--paths", "a.py"), "D2 (lease L2 held by perf/D2)")
            self.assertEqual(self.brigade("dish", "D2", "--state", "dropped"), "D2 dropped; T1 waiting again")
            self.brigade("ticket", "set", "T1", "--state", "dropped")
            self.brigade("set", "--intake", "")
            self.assertEqual(self.land("lease", "list"), "no leases held")

    def test_dropping_an_item_leaves_its_other_tickets_alone(self):
        self.open()
        for summary in ("one", "two"):
            self.brigade("ticket", "add", "--summary", summary)
        self.brigade("fire", "--tickets", "T1", "--station", "bug-fix", "--summary", "a")
        self.brigade("fire", "--tickets", "T2", "--station", "bug-fix", "--summary", "b")
        self.brigade("ticket", "set", "T2", "--state", "done")
        self.assertEqual(self.brigade("dish", "D2", "--state", "dropped"), "D2 dropped")
        self.assertEqual(self.brigade("ticket", "list"), "T1 assigned [user] one\nT2 done [user] two")

    def test_blocked_counts_follow_the_block_that_holds_now(self):
        from unittest import mock
        self.init_landing()
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": self.land_env()["XDG_STATE_HOME"]}):
            self.open()
            self.brigade("ticket", "add", "--summary", "Fix the gate")
            self.land("lease", "claim", "--holder", "engine/D1", "--paths", "src")
            self.brigade("fire", "--tickets", "T1", "--station", "bug-fix", "--summary", "Fix the gate",
                         "--paths", "src", ok=False)
            self.assertEqual(self.brigade("ticket", "list"), "T1 waiting [user] Fix the gate blocked: lease")
            self.assertIn("Perf (reports milestones): waiting tickets: 1 (1 blocked)", self.brigade("walk"))
            self.land("lease", "release", "L1")
            self.assertTrue(self.brigade("watch").startswith("T1: unblocked; run fire"))
            self.assertEqual(self.brigade("ticket", "list"), "T1 waiting [user] Fix the gate")
            self.assertIn("Perf (reports milestones): waiting tickets: 1\n", self.brigade("walk") + "\n")
            self.land("lease", "claim", "--holder", "engine/D2", "--paths", "src")
            self.assertEqual(self.brigade("ticket", "list"), "T1 waiting [user] Fix the gate blocked: lease")

    def test_fire_and_watch_name_the_worker_cap_first_when_both_caps_hold(self):
        from unittest import mock
        self.init_landing("--cap", "1")
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": self.land_env()["XDG_STATE_HOME"]}):
            self.brigade("open", "--project-root", str(self.project), "--name", "Perf", "--workers", "1")
            self.brigade("ticket", "add", "--summary", "one")
            self.brigade("ticket", "add", "--summary", "two")
            self.brigade("fire", "--tickets", "T1", "--station", "bug-fix", "--summary", "one", "--paths", "src")
            refused = self.brigade("fire", "--tickets", "T2", "--station", "bug-fix", "--summary", "two",
                                   "--paths", "docs", ok=False)
            self.assertEqual(refused, "brigade: nothing fired: 1 of 1 workers running")
            self.assertEqual(self.brigade("watch").splitlines()[-1], "T2: waiting for a worker (1 of 1 running)")
            self.assertEqual(self.brigade("ticket", "list", "--state", "waiting"), "T2 waiting [user] two blocked: workers")
            self.brigade("set", "--workers", "2")
            self.assertEqual(self.brigade("watch").splitlines()[-1],
                             "T2: waiting for room in the repository (1 of 1 changes in flight)")
            self.assertEqual(self.brigade("ticket", "list", "--state", "waiting"),
                             "T2 waiting [user] two blocked: repository")

    def renamed(self, hook=None):
        """Fire D1 on perf/d1, then run dish D1 --branch perf/d1-r2 in this process, calling hook at its lease list."""
        self.open()
        self.brigade("set", "--thread", "coordinator")
        self.brigade("ticket", "add", "--summary", "one")
        self.brigade("fire", "--tickets", "T1", "--station", "bug-fix", "--summary", "s",
                     "--branch", "perf/d1", "--paths", "src")
        glob = runpy.run_path(str(SCRIPT))["run"].__globals__
        original = glob["land_result"]

        def hooked(project_root, *args):
            if hook and args[:2] == ("lease", "list"):
                hook()
            return original(project_root, *args)

        glob["land_result"] = hooked
        argv = ["--store", str(self.store), "--at", str(self.at), "--owner", "coordinator@1",
                "dish", "D1", "--branch", "perf/d1-r2"]
        try:
            return glob["run"](argv)
        except glob["BrigadeError"] as error:
            return f"brigade: {error}"

    def lease_lines(self):
        return [line.split(" until ")[0] + ": " + line.rsplit(": ", 1)[1]
                for line in self.land("lease", "list").splitlines()]

    def test_a_new_branch_prints_the_commands_that_lease_its_fragment(self):
        from unittest import mock
        self.init_landing("--cap", "3")
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": self.land_env()["XDG_STATE_HOME"]}):
            wide = "src,changes/perf%2Fd1.md,changes/perf%2Fd1-r2.md"
            self.assertEqual(self.renamed(), "\n".join([
                "D1 in-progress",
                "D1: L1 does not cover changes/perf%2Fd1-r2.md; cover it with these commands:",
                f"  $L lease claim --holder perf/D1 --paths {wide} --owner perf/@1",
                f"  $B dish D1 --lease <new lease> --paths {wide}",
                "  $L lease release L1 --owner perf/@1",
            ]))
            row = self.table_row(self.at, "dishes.tsv", "D1")
            self.assertEqual((row["branch"], row["lease"], row["paths"]), ("perf/d1-r2", "L1", "src,changes/perf%2Fd1.md"))
            self.assertEqual(self.lease_lines(), ["L1 active perf/D1: changes/perf%2Fd1.md, src"])
            self.assertEqual(self.land("lease", "claim", "--holder", "perf/D1", "--paths", wide, "--owner", "perf/@1"), "L2")
            self.assertEqual(self.brigade("dish", "D1", "--lease", "L2", "--paths", wide), "D1 in-progress")
            self.land("lease", "release", "L1", "--owner", "perf/@1")
            self.assertEqual(self.lease_lines(), ["L2 active perf/D1: changes/perf%2Fd1-r2.md, changes/perf%2Fd1.md, src"])
            self.assertEqual(self.brigade("dish", "D1", "--branch", "perf/d1-r2"), "D1 in-progress")

    def test_a_branch_rename_during_a_drop_leaves_no_lease(self):
        from unittest import mock
        self.init_landing("--cap", "3")
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": self.land_env()["XDG_STATE_HOME"]}):
            dropped = []
            result = self.renamed(lambda: dropped or dropped.append(self.brigade("dish", "D1", "--state", "dropped")))
            self.assertEqual(dropped, ["D1 dropped; T1 waiting again"])
            self.assertEqual(result, "D1 in-progress")
            self.assertEqual(self.land("lease", "list"), "no leases held")
            refused = self.brigade("dish", "D1", "--lease", "L2", "--paths", "src", ok=False)
            self.assertEqual(refused, "brigade: D1 is dropped; it holds no lease")
            self.assertEqual(self.land("lease", "claim", "--holder", "engine/D1", "--paths", "src"), "L2")
            self.assertEqual(self.brigade("watch"), "no work in progress")

    def test_a_branch_rename_by_a_replaced_owner_claims_nothing(self):
        from unittest import mock
        self.init_landing("--cap", "3")
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": self.land_env()["XDG_STATE_HOME"]}):
            taken = []
            result = self.renamed(lambda: taken or taken.append(
                self.brigade("set", "--thread", "replacement", "--replace")))
            self.assertEqual(len(taken), 1)
            self.assertIn("$L lease claim --holder perf/D1", result)
            self.assertEqual(self.lease_lines(), ["L1 active perf/D1: changes/perf%2Fd1.md, src"])
            stale = self.run_at(self.at, "--owner", "coordinator@1", "dish", "D1", "--branch", "perf/d1-r3", ok=False)
            self.assertEqual(stale, "brigade: owner coordinator@1 is stale; this store is owned by replacement@2")
            self.assertEqual(self.table_row(self.at, "dishes.tsv", "D1")["branch"], "perf/d1-r2")
            self.assertEqual(self.brigade("dish", "D1", "--state", "dropped"), "D1 dropped; T1 waiting again")
            self.assertEqual(self.land("lease", "list"), "no leases held")

    def test_a_branch_rename_after_submit_says_the_lease_cannot_change(self):
        self.init_landing("--cap", "3")
        from unittest import mock
        with mock.patch.dict(os.environ, self.land_env()):
            self.open()
            self.brigade("ticket", "add", "--summary", "one")
            self.brigade("fire", "--tickets", "T1", "--station", "bug-fix", "--summary", "one",
                         "--branch", "perf/d1", "--paths", "a.txt")
            sha = self.worker_commit("perf/d1", {"a.txt": "changed\n"})
            self.passed(sha)
            self.submit(sha)
            self.brigade("dish", "D1", "--state", "queued")
            self.assertEqual(self.brigade("dish", "D1", "--branch", "perf/d1-r2"), "\n".join([
                "D1 queued",
                "D1: L1 is submitted, so it cannot take changes/perf%2Fd1-r2.md; the submitted commit lands as it is. "
                "Run dish D1 --branch perf/d1-r2 again if its entry bounces",
            ]))
            self.assertEqual(self.lease_lines(), ["L1 submitted perf/D1: a.txt, changes/perf%2Fd1.md"])

    def test_open_prints_the_sibling_on_the_same_project_root(self):
        self.open()
        menu = (self.at / "menu.md").read_text()
        menu = menu.replace(
            "What this restaurant exists to achieve, in one or two sentences.",
            "Keep startup under 400 ms.")
        menu = menu.replace(
            "Work this restaurant does not take, even when asked.",
            "Docs and release notes\nVendor upgrades")
        (self.at / "menu.md").write_text(menu)
        self.brigade("set", "--thread", "thread-perf")
        docs_dir = self.store / "bridge-kit" / "docs"
        self.assertEqual(
            self.brigade("open", "--project-root", str(self.project), "--name", "Docs"),
            "\n".join([
                f"opened {docs_dir}",
                f"sibling Perf ({self.at}), thread thread-perf",
                "  purpose: Keep startup under 400 ms.",
                "  off the menu: Docs and release notes; Vendor upgrades",
            ]))
        self.assertEqual(
            self.brigade("open", "--project-root", str(self.project), "--name", "Perf"),
            "\n".join([
                f"exists {self.at}",
                "thread thread-perf already recorded",
                f"sibling Docs ({docs_dir}), thread not recorded",
                "  purpose: not written yet",
                "  off the menu: not written yet",
            ]))

    def test_open_refuses_a_directory_that_holds_another_project_root(self):
        first = (Path(self.temporary.name) / "left" / "app").resolve()
        second = (Path(self.temporary.name) / "right" / "app").resolve()
        first.mkdir(parents=True)
        second.mkdir(parents=True)
        directory = self.store / "app" / "docs"
        self.assertEqual(
            self.brigade("open", "--project-root", str(first), "--name", "Docs"),
            f"opened {directory}")
        before = (directory / "restaurant.json").read_bytes()
        error = self.brigade("open", "--project-root", str(second), "--name", "Docs", ok=False)
        self.assertEqual(
            error,
            f"brigade: {directory} already holds a coordinator for {first}; pick another --name")
        self.assertEqual((directory / "restaurant.json").read_bytes(), before)

    def test_two_processes_opening_one_name_on_different_roots_leave_one_store(self):
        roots = []
        for label in ("left", "right"):
            path = (Path(self.temporary.name) / label / "app").resolve()
            path.mkdir(parents=True)
            roots.append(path)
        directory = self.store / "app" / "docs"
        procs = [
            subprocess.Popen(
                [sys.executable, str(SCRIPT), "--store", str(self.store),
                 "open", "--project-root", str(root), "--name", "Docs"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            for root in roots
        ]
        finished = []
        for proc in procs:
            out, err = proc.communicate(timeout=15)
            finished.append((proc.returncode, out, err))
        self.assertEqual(sorted(code for code, _, _ in finished), [0, 1])
        self.assertEqual(len(list((directory.parent).glob("*/restaurant.json"))), 1)
        meta = json.loads((directory / "restaurant.json").read_text())
        winner = next(item for item in finished if item[0] == 0)
        loser = next(item for item in finished if item[0] == 1)
        self.assertIn(meta["projectRoot"], [str(root) for root in roots])
        self.assertTrue(winner[1].startswith(f"opened {directory}"))
        self.assertIn(f"already holds a coordinator for {meta['projectRoot']}", loser[2])
        self.assertIn("pick another --name", loser[2])

    def test_set_thread_refuses_to_replace_a_recorded_thread(self):
        self.open()
        self.brigade("set", "--thread", "thread-1")
        self.brigade("set", "--thread", "thread-1")
        before = (self.at / "restaurant.json").read_bytes()
        error = self.brigade("set", "--thread", "thread-2", ok=False)
        self.assertEqual(error, "brigade: thread thread-1 already recorded")
        self.assertEqual((self.at / "restaurant.json").read_bytes(), before)
        self.brigade("set", "--thread", "thread-2", "--replace")
        self.assertEqual(json.loads((self.at / "restaurant.json").read_text())["thread"], "thread-2")

    def _spawn_race(self, mode, case, args):
        return subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--race-child", mode, str(case), *args],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))

    def _finish_race(self, proc):
        try:
            out, err = proc.communicate(timeout=12)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, err = proc.communicate()
            self.fail(f"timed out\nstdout:\n{out}\nstderr:\n{err}")
        return proc.returncode, out.strip(), err.strip()

    def test_a_losing_open_keeps_the_owners_ticket_and_menu(self):
        case = Path(self.temporary.name) / "race"
        case.mkdir()
        project = Path(self.temporary.name) / "app"
        project.mkdir()
        directory = self.store / "app" / "docs"
        args = ["--store", str(self.store), "open", "--project-root", str(project), "--name", "Docs"]
        owner = loser = None
        try:
            owner = self._spawn_race("owner", case, args)
            _wait_for_path(case / "metadata-ready")
            loser = self._spawn_race("loser", case, args)
            _wait_for_path(case / "loser-saw-meta")
            self.assertIsNone(owner.poll())
            self.assertIsNone(loser.poll())
            if not (directory / "rail.tsv").exists():
                (case / "loser-after-meta").touch()
                _wait_for_path(case / "loser-at-scaffold")
                (case / "owner-proceed").touch()
                owner_code, owner_out, owner_err = self._finish_race(owner)
                owner = None
            else:
                owner_code = owner_out = owner_err = None
            added = subprocess.run(
                [sys.executable, str(SCRIPT), "--at", str(directory), "ticket", "add", "--summary", "Keep this ticket"],
                capture_output=True, text=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
            self.assertEqual((added.returncode, added.stdout), (0, "T1\n"), added.stderr)
            menu = directory / "menu.md"
            menu.write_text(menu.read_text() + "Keep the menu sentence.\n")
            if (case / "loser-at-scaffold").exists():
                (case / "loser-scaffold-proceed").touch()
            else:
                (case / "loser-after-meta").touch()
            loser_code, loser_out, loser_err = self._finish_race(loser)
            loser = None
            if owner is not None:
                (case / "owner-proceed").touch()
                owner_code, owner_out, owner_err = self._finish_race(owner)
                owner = None
        finally:
            for proc in (owner, loser):
                if proc is not None and proc.poll() is None:
                    proc.kill()
                    proc.wait(timeout=5)
        self.assertEqual((owner_code, owner_err), (0, ""), owner_out)
        self.assertEqual(owner_out, f"opened {directory}")
        self.assertEqual((loser_code, loser_err), (0, ""), loser_out)
        self.assertEqual(loser_out, f"exists {directory}")
        self.assertIn("Keep this ticket", (directory / "rail.tsv").read_text())
        self.assertIn("Keep the menu sentence.", (directory / "menu.md").read_text())

    def test_open_rejects_a_restaurant_json_that_is_not_valid_json(self):
        self.at.mkdir(parents=True)
        (self.at / "restaurant.json").write_text('{"restaurant":')
        started = time.monotonic()
        error = self.brigade("open", "--project-root", str(self.project), "--name", "Perf", ok=False)
        elapsed = time.monotonic() - started
        self.assertEqual(error, f"brigade: {self.at / 'restaurant.json'} is not valid JSON")
        self.assertGreaterEqual(elapsed, 0.9)
        self.assertLess(elapsed, 3)
        self.assertEqual((self.at / "restaurant.json").read_text(), '{"restaurant":')
        self.assertFalse((self.at / "menu.md").exists())
        self.assertFalse((self.at / "rail.tsv").exists())

    def test_open_accepts_restaurant_json_that_becomes_valid_within_one_second(self):
        self.at.mkdir(parents=True)
        path = self.at / "restaurant.json"
        path.write_text('{"restaurant":')
        proc = subprocess.Popen(
            [sys.executable, str(SCRIPT), "--store", str(self.store), "open",
             "--project-root", str(self.project), "--name", "Perf"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        try:
            time.sleep(0.2)
            self.assertIsNone(proc.poll())
            path.write_text(json.dumps({
                "restaurant": "Perf",
                "projectRoot": str(self.project.resolve()),
                "landing": "merge",
                "thread": None,
                "schedules": {},
            }))
            out, err = proc.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, err = proc.communicate()
            self.fail(f"timed out\nstdout:\n{out}\nstderr:\n{err}")
        self.assertEqual((proc.returncode, err.strip()), (0, ""), out)
        self.assertTrue(out.startswith(f"exists {self.at}"))


    def git_project(self):
        if (self.project / ".git").exists():
            return
        run = lambda *command: subprocess.run(command, cwd=self.project, capture_output=True, text=True, check=True)
        run("git", "init", "-q", "-b", "main")
        (self.project / "a.txt").write_text("a\n")
        run("git", "add", "-A")
        run("git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")

    def land_env(self):
        return dict(os.environ, XDG_STATE_HOME=str(Path(self.temporary.name) / "state"))

    def land_repo(self, repo, *args, ok=True):
        result = subprocess.run([sys.executable, str(ROOT / "t3/added/landing/scripts/land.py"),
                                 "--repo", str(repo), *args],
                                capture_output=True, text=True, env=self.land_env())
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        return (result.stdout if ok else result.stderr).strip()

    def land(self, *args, ok=True):
        return self.land_repo(self.project, *args, ok=ok)

    def init_landing(self, *args):
        self.git_project()
        return self.land("init", "--trunk", "lane", "--mode", "local", "--base", "main", *args)

    def test_a_refused_fire_stays_blocked_until_the_lease_is_free(self):
        from unittest import mock
        self.init_landing()
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": self.land_env()["XDG_STATE_HOME"]}):
            self.open()
            self.brigade("ticket", "add", "--summary", "Fix the gate")
            self.land("lease", "claim", "--holder", "engine/D1", "--paths", "src")
            refused = self.brigade("fire", "--tickets", "T1", "--station", "bug-fix", "--summary", "Fix the gate",
                                   "--paths", "src", "--timebox", "60", ok=False)
            self.assertIn("nothing fired: paths overlap L1 held by engine/D1", refused)
            self.assertEqual(self.brigade("ticket", "list"), "T1 waiting [user] Fix the gate blocked: lease")
            self.assertEqual(self.brigade("watch"), "T1: waiting on L1 (engine/D1)")
            self.land("lease", "release", "L1")
            self.land("lease", "claim", "--holder", "engine/D1", "--paths", "src")
            self.assertEqual(self.brigade("watch"), "T1: waiting on L2 (engine/D1)")
            self.land("lease", "release", "L2")
            line = "T1: unblocked; run fire --tickets=T1 --station=bug-fix '--summary=Fix the gate' --paths=src --timebox=60"
            self.assertEqual(self.brigade("watch"), line)
            started = self.brigade(*shlex.split(line.split("run ", 1)[1]))
            self.assertEqual(started, "D1 (lease L3 held by perf/D1)")
            self.assertEqual(self.table_row(self.at, "dishes.tsv", "D1")["paths"], "src,changes/perf%2Fd1.md")
            self.assertEqual(self.brigade("ticket", "list"), "T1 assigned [user] Fix the gate")

    def test_an_unblocked_command_round_trips_through_bash(self):
        from unittest import mock
        marker = Path(self.temporary.name) / "shell-marker"
        summary = f"Fix O'Reilly; touch {marker}; # $(touch {marker}) & spaces"
        self.init_landing()
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": self.land_env()["XDG_STATE_HOME"]}):
            self.open()
            self.brigade("ticket", "add", "--summary", "quoted")
            self.land("lease", "claim", "--holder", "engine/D1", "--paths", "src/app.py")
            refused = self.brigade("fire", "--tickets", "T1", "--station", "bug-fix", "--summary", summary,
                                   "--branch", "docs/gate", "--paths", "src/app.py", "--timebox", "45", ok=False)
            self.assertIn("nothing fired: paths overlap L1 held by engine/D1", refused)
            self.land("lease", "release", "L1")
            line = self.brigade("watch")
            ran = self.bash_unblocked(self.at, line)
        self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
        self.assertFalse(marker.exists(), ran.stdout + ran.stderr)
        row = self.table_row(self.at, "dishes.tsv", "D1")
        self.assertEqual(row["summary"], summary)
        self.assertEqual(row["paths"], "src/app.py,changes/docs%2Fgate.md")
        self.assertEqual(row["timebox"], "45")
        self.assertEqual(row["branch"], "docs/gate")

    def test_an_option_leading_summary_round_trips_through_bash(self):
        self.brigade("open", "--project-root", str(self.project), "--name", "Perf",
                     "--workers", "1")
        self.brigade("ticket", "add", "--summary", "seed")
        self.brigade("fire", "--tickets", "T1", "--station", "bug-fix", "--summary", "seed")
        blocker = "D1"
        cases = (("-Werror", "T2", "D2"), ("--help", "T3", "D3"))
        for summary, ticket, dish in cases:
            self.brigade("ticket", "add", f"--summary={summary}")
            refused = self.brigade("fire", "--tickets", ticket, "--station", "bug-fix",
                                   f"--summary={summary}", "--timebox", "45", ok=False)
            self.assertIn("nothing fired: 1 of 1 workers running", refused)
            self.brigade("dish", blocker, "--state", "sent-back")
            line = next(part for part in self.brigade("watch").splitlines() if part.startswith(f"{ticket}: unblocked"))
            ran = self.bash_unblocked(self.at, line)
            self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
            row = self.table_row(self.at, "dishes.tsv", dish)
            self.assertEqual(row["summary"], summary)
            self.assertEqual(row["timebox"], "45")
            self.assertEqual(row["station"], "bug-fix")
            blocker = dish

    def test_a_later_fire_does_not_keep_the_refused_attempts_fragment(self):
        from unittest import mock
        self.init_landing()
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": self.land_env()["XDG_STATE_HOME"]}):
            directory = self.store / "bridge-kit" / "review-more"
            opened = self.brigade("open", "--project-root", str(self.project), "--name", "Review more")
            self.assertEqual(opened, f"opened {directory}")
            self.run_at(directory, "ticket", "add", "--summary", "Blocked on src")
            self.run_at(directory, "ticket", "add", "--summary", "Takes the first id")
            self.land("lease", "claim", "--holder", "engine/D9", "--paths", "src")
            refused = self.run_at(directory, "fire", "--tickets", "T1", "--station", "bug-fix",
                                  "--summary", "Blocked on src", "--paths", "src", "--timebox", "30", ok=False)
            self.assertIn("nothing fired: paths overlap L1 held by engine/D9", refused)
            note = self.blocked_note(directory, "T1")
            self.assertEqual(note["paths"], "src")
            self.assertNotIn("branch", note)
            started = self.run_at(directory, "fire", "--tickets", "T2", "--station", "bug-fix",
                                  "--summary", "Takes the first id", "--paths", "other")
            self.assertEqual(started, "D1 (lease L2 held by review-more/D1)")
            self.assertEqual(self.table_row(directory, "dishes.tsv", "D1")["paths"], "other,changes/review-more%2Fd1.md")
            self.land("lease", "release", "L1")
            line = self.run_at(directory, "watch")
            self.assertNotIn("waiting on", line)
            self.assertIn("--paths=src --timebox=30", line)
            self.assertNotIn("changes/review-more%2Fd1.md", line)
            ran = self.bash_unblocked(directory, line)
        self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
        row = self.table_row(directory, "dishes.tsv", "D2")
        self.assertEqual(row["paths"], "src,changes/review-more%2Fd2.md")
        self.assertEqual(row["branch"], "")
        self.assertEqual(row["timebox"], "30")
        self.assertEqual(row["summary"], "Blocked on src")

    def test_a_refused_fire_keeps_an_explicit_branch(self):
        from unittest import mock
        self.init_landing()
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": self.land_env()["XDG_STATE_HOME"]}):
            directory = self.store / "bridge-kit" / "review"
            opened = self.brigade("open", "--project-root", str(self.project), "--name", "Review")
            self.assertEqual(opened, f"opened {directory}")
            self.run_at(directory, "ticket", "add", "--summary", "Explicit branch")
            self.land("lease", "claim", "--holder", "engine/D1", "--paths", "src")
            refused = self.run_at(directory, "fire", "--tickets", "T1", "--station", "bug-fix",
                                  "--summary", "Explicit branch", "--branch", "docs/a%b/c",
                                  "--paths", "src,changes/docs%2Fa%25b%2Fc.md", ok=False)
            self.assertIn("nothing fired: paths overlap L1 held by engine/D1", refused)
            note = self.blocked_note(directory, "T1")
            self.assertEqual(note["paths"], "src,changes/docs%2Fa%25b%2Fc.md")
            self.assertEqual(note.get("branch"), "docs/a%b/c")
            self.land("lease", "release", "L1")
            line = self.run_at(directory, "watch")
            self.assertIn("--branch", line)
            self.assertIn("docs/a%b/c", line)
            ran = self.bash_unblocked(directory, line)
        self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
        row = self.table_row(directory, "dishes.tsv", "D1")
        self.assertEqual(row["branch"], "docs/a%b/c")
        self.assertEqual(row["paths"], "src,changes/docs%2Fa%25b%2Fc.md")
        self.assertEqual(row["summary"], "Explicit branch")
        self.assertNotIn("changes/review%2Fd1.md", row["paths"])

    def test_a_worker_refusal_prints_the_running_count(self):
        self.brigade("open", "--project-root", str(self.project), "--name", "Perf", "--workers", "3")
        for number, summary in enumerate(("one", "two", "three"), start=1):
            self.brigade("ticket", "add", "--summary", summary)
            self.brigade("fire", "--tickets", f"T{number}", "--station", "bug-fix", "--summary", summary)
        self.brigade("ticket", "add", "--summary", "four")
        self.brigade("set", "--workers", "1")
        refused = self.brigade("fire", "--tickets", "T4", "--station", "bug-fix", "--summary", "four", ok=False)
        self.assertIn("nothing fired: 3 of 1 workers running", refused)
        self.assertIn("T4: waiting for a worker (3 of 1 running)", self.brigade("watch"))

    def test_a_failed_lease_check_keeps_the_landing_diagnostic(self):
        case = Path(self.temporary.name)
        (case / "land.py").write_text(
            "import sys\n"
            "action = sys.argv[4]\n"
            "if action == 'claim':\n"
            "    print('paths overlap L1 held by engine/D1 on src', file=sys.stderr)\n"
            "    sys.exit(1)\n"
            "if action == 'check':\n"
            "    print('queue database is locked', file=sys.stderr)\n"
            "    sys.exit(1)\n"
            "sys.exit(0)\n")
        self.open()
        self.brigade("ticket", "add", "--summary", "one")
        refused = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--race-child", "fake-land", str(case),
                                  "--store", str(self.store), "--at", str(self.at),
                                  "fire", "--tickets", "T1", "--station", "bug-fix", "--summary", "s", "--paths", "src"],
                                 capture_output=True, text=True)
        self.assertNotEqual(refused.returncode, 0, refused.stdout + refused.stderr)
        watched = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--race-child", "fake-land", str(case),
                                  "--store", str(self.store), "--at", str(self.at), "watch"],
                                 capture_output=True, text=True)
        self.assertEqual(watched.returncode, 0, watched.stderr)
        self.assertEqual(watched.stdout.strip(), "T1: waiting on the landing queue (queue database is locked)")

    def test_a_repository_cap_refusal_prints_the_repository_line(self):
        from unittest import mock
        self.init_landing("--cap", "1")
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": self.land_env()["XDG_STATE_HOME"]}):
            self.open()
            self.brigade("ticket", "add", "--summary", "Room")
            self.land("lease", "claim", "--holder", "engine/D1", "--paths", "other.txt")
            refused = self.brigade("fire", "--tickets", "T1", "--station", "bug-fix", "--summary", "Room",
                                   "--paths", "src", ok=False)
            self.assertIn("nothing fired: repository at its cap: 1 of 1 changes in flight", refused)
            self.assertIn("blocked: repository", self.brigade("ticket", "list"))
            self.assertEqual(self.brigade("watch"), "T1: waiting for room in the repository (1 of 1 changes in flight)")

    def test_the_worker_cap_defaults_to_two_and_a_later_fire_clears_the_block(self):
        self.open()
        self.assertNotIn("workers", json.loads((self.at / "restaurant.json").read_text()))
        for summary in ("one", "two", "three"):
            self.brigade("ticket", "add", "--summary", summary)
        self.assertEqual(self.brigade("fire", "--tickets", "T1", "--station", "bug-fix", "--summary", "a"), "D1")
        self.assertEqual(self.brigade("fire", "--tickets", "T2", "--station", "bug-fix", "--summary", "b"), "D2")
        refused = self.brigade("fire", "--tickets", "T3", "--station", "bug-fix", "--summary", "c", ok=False)
        self.assertIn("nothing fired: 2 of 2 workers running", refused)
        self.assertEqual(self.brigade("ticket", "list", "--state", "waiting"),
                         "T3 waiting [user] three blocked: workers")
        self.assertIn("T3: waiting for a worker (2 of 2 running)", self.brigade("watch"))
        self.brigade("set", "--workers", "3")
        self.assertEqual(self.brigade("fire", "--tickets", "T3", "--station", "bug-fix", "--summary", "c"), "D3")
        self.assertNotIn("blocked:", self.brigade("ticket", "list"))

    def test_workers_one_refuses_fire_and_a_dish_that_is_not_already_counted(self):
        opened = self.brigade("open", "--project-root", str(self.project), "--name", "Perf",
                              "--workers", "1")
        self.assertEqual(opened, f"opened {self.at}")
        self.assertEqual(json.loads((self.at / "restaurant.json").read_text())["workers"], 1)
        for summary in ("one", "two", "three"):
            self.brigade("ticket", "add", "--summary", summary)
        self.assertEqual(self.brigade("fire", "--tickets", "T1", "--station", "bug-fix", "--summary", "a"), "D1")
        refused = self.brigade("fire", "--tickets", "T2", "--station", "bug-fix", "--summary", "b", ok=False)
        self.assertIn("nothing fired: 1 of 1 workers running", refused)
        self.brigade("dish", "D1", "--state", "sent-back")
        self.assertEqual(self.brigade("fire", "--tickets", "T2", "--station", "bug-fix", "--summary", "b"), "D2")
        self.brigade("dish", "D2", "--state", "blocked")
        self.assertEqual(self.brigade("fire", "--tickets", "T3", "--station", "bug-fix", "--summary", "c"), "D3")
        sent = self.brigade("dish", "D1", "--state", "in-progress", ok=False)
        review = self.brigade("dish", "D2", "--state", "in-review", ok=False)
        self.assertIn("1 of 1 workers running", sent)
        self.assertIn("1 of 1 workers running", review)
        self.assertEqual(self.brigade("dish", "D3", "--state", "in-review"), "D3 in-review")
        self.assertEqual(self.brigade("dish", "D3", "--state", "in-progress", "--thread", "worker-2"), "D3 in-progress")
        before = (self.at / "restaurant.json").read_text()
        error = self.brigade("set", "--workers", "0", ok=False)
        self.assertIn("workers must be 1 or more", error)
        self.assertEqual((self.at / "restaurant.json").read_text(), before)
        missing = self.brigade("open", "--project-root", str(self.project), "--name", "Nope",
                               "--workers", "0", ok=False)
        self.assertIn("workers must be 1 or more", missing)
        self.assertFalse((self.store / "bridge-kit" / "nope").exists())

    def test_open_warns_when_workers_meet_the_repository_cap_and_a_sibling_exists(self):
        from unittest import mock
        self.init_landing("--cap", "2")
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": self.land_env()["XDG_STATE_HOME"]}):
            first = self.brigade("open", "--project-root", str(self.project), "--name", "Perf",
                                 "--workers", "4")
            self.assertNotIn("warning:", first)
            second = self.brigade("open", "--project-root", str(self.project), "--name", "Docs",
                                  "--workers", "2")
            self.assertIn("warning: workers 2 is at or above the repository cap of 2 while a sibling exists", second)
            third = self.brigade("open", "--project-root", str(self.project), "--name", "Quiet",
                                 "--workers", "1")
            self.assertNotIn("warning:", third)

    def test_fire_leases_the_branch_changelog_fragment_and_dish_records_a_new_lease(self):
        from unittest import mock
        self.init_landing()
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": self.land_env()["XDG_STATE_HOME"]}):
            self.open()
            (self.at / "menu.md").write_text("## Purpose\n\nFast.\n")
            self.brigade("set", "--thread", "thread-coord")
            self.brigade("ticket", "add", "--summary", "one")
            self.brigade("ticket", "add", "--summary", "two")
            self.brigade("fire", "--tickets", "T1", "--station", "bug-fix", "--summary", "s",
                         "--branch", "docs/a", "--paths", "src/a.py")
            text = self.brigade("brief", "D1", "--goal", "g", "--acceptance", "a", "--verify", "v", "--base", "origin/main")
            self.assertIn("leased to you as L1: src/a.py,changes/docs%2Fa.md.", text)
            self.brigade("fire", "--tickets", "T2", "--station", "bug-fix", "--summary", "s",
                         "--branch", "docs/a%b", "--paths", "src/b.py")
            text = self.brigade("brief", "D2", "--goal", "g", "--acceptance", "a", "--verify", "v", "--base", "origin/main")
            self.assertIn("leased to you as L2: src/b.py,changes/docs%2Fa%25b.md.", text)
            self.assertEqual(text.count("changes/docs%2Fa%25b.md"), 1)
            self.brigade("dish", "D1", "--lease", "L9", "--paths", "src/a.py,changes/docs%2Fa.md")
            text = self.brigade("brief", "D1", "--goal", "g", "--acceptance", "a", "--verify", "v", "--base", "origin/main")
            self.assertIn("leased to you as L9: src/a.py,changes/docs%2Fa.md.", text)

    def test_fire_warns_when_releasing_a_conflicting_lease_fails(self):
        case = Path(self.temporary.name)
        (case / "land.py").write_text(
            "import sys, time\nfrom pathlib import Path\n"
            f"case = Path({str(case)!r})\n"
            "with open(case / 'land-calls', 'a') as handle:\n    handle.write(' '.join(sys.argv[3:]) + '\\n')\n"
            "if sys.argv[4] == 'claim':\n"
            "    (case / 'claiming').touch()\n"
            "    end = time.monotonic() + 30\n"
            "    while not (case / 'claim-proceed').exists() and time.monotonic() < end:\n        time.sleep(0.01)\n"
            "    print('L7')\n"
            "else:\n"
            "    print('lease L7 is held elsewhere', file=sys.stderr)\n"
            "    sys.exit(1)\n")
        self.open()
        self.brigade("ticket", "add", "--summary", "one")
        firing = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--race-child", "fake-land", str(case),
                                   "--store", str(self.store), "--at", str(self.at),
                                   "fire", "--tickets", "T1", "--station", "bug-fix", "--summary", "s", "--paths", "src"],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                  env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        try:
            _wait_for_path(case / "claiming")
            other = subprocess.run([sys.executable, str(SCRIPT), "--store", str(self.store), "--at", str(self.at),
                                    "fire", "--tickets", "T1", "--station", "bug-fix", "--summary", "other"],
                                   capture_output=True, text=True, timeout=10)
            self.assertEqual(other.stdout.strip(), "D1", other.stderr)
            (case / "claim-proceed").touch()
            _, err = firing.communicate(timeout=10)
        finally:
            firing.kill()
        self.assertEqual(firing.returncode, 1)
        self.assertIn("nothing fired: T1 is assigned, not waiting", err)
        self.assertIn("L7", err)
        self.assertIn("lease L7 is held elsewhere", err)

    def test_watch_rechecks_a_lease_outside_the_store_lock(self):
        case = Path(self.temporary.name)
        (case / "land.py").write_text(
            "import sys, time\nfrom pathlib import Path\n"
            f"case = Path({str(case)!r})\n"
            "action = sys.argv[4]\n"
            "if action == 'claim':\n"
            "    print('paths overlap L1 held by engine/D1 on src', file=sys.stderr)\n"
            "    sys.exit(1)\n"
            "if action == 'check':\n"
            "    (case / 'checking').touch()\n"
            "    end = time.monotonic() + 30\n"
            "    while not (case / 'check-proceed').exists() and time.monotonic() < end:\n        time.sleep(0.01)\n"
            "    print('L1 held by engine/D1 on src')\n"
            "    sys.exit(1)\n"
            "print('ok')\n")
        self.open()
        self.brigade("ticket", "add", "--summary", "one")
        refused = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--race-child", "fake-land", str(case),
                                  "--store", str(self.store), "--at", str(self.at),
                                  "fire", "--tickets", "T1", "--station", "bug-fix", "--summary", "s", "--paths", "src"],
                                 capture_output=True, text=True)
        self.assertNotEqual(refused.returncode, 0, refused.stdout + refused.stderr)
        self.assertIn("blocked: lease", self.brigade("ticket", "list"))
        watching = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--race-child", "fake-land", str(case),
                                     "--store", str(self.store), "--at", str(self.at), "watch"],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                    env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        try:
            _wait_for_path(case / "checking")
            added = subprocess.run([sys.executable, str(SCRIPT), "--store", str(self.store), "--at", str(self.at),
                                    "ticket", "add", "--summary", "two"],
                                   capture_output=True, text=True, timeout=10)
            self.assertEqual(added.stdout.strip(), "T2", added.stderr)
            (case / "check-proceed").touch()
            out, err = watching.communicate(timeout=10)
        finally:
            watching.kill()
        self.assertEqual(watching.returncode, 0, err)
        self.assertEqual(out.strip(), "T1: waiting on L1 (engine/D1)")

    def landing_env(self):
        from unittest import mock
        patcher = mock.patch.dict(os.environ, {"XDG_STATE_HOME": self.land_env()["XDG_STATE_HOME"]})
        patcher.start()
        self.addCleanup(patcher.stop)

    def started(self, *init, paths="README.md"):
        """A local landing contract, the Perf coordinator, and D1 holding L1."""
        self.init_landing(*init)
        self.landing_env()
        self.open()
        (self.at / "menu.md").write_text("## Purpose\n\nFast.\n")
        self.brigade("ticket", "add", "--summary", "one")
        self.assertEqual(self.brigade("fire", "--tickets", "T1", "--station", "bug-fix", "--summary", "s", "--paths", paths),
                         "D1 (lease L1 held by perf/D1)")

    def backdate_attempt(self, minutes, ident="D1"):
        start = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
        log = self.at / "log.tsv"
        lines = log.read_text().splitlines()
        rewritten = [lines[0]]
        found = False
        for line in lines[1:]:
            fields = line.split("\t")
            if fields[1:4] == ["dish", ident, "in-progress"]:
                fields[0] = start
                line = "\t".join(fields)
                found = True
            rewritten.append(line)
        self.assertTrue(found, ident)
        log.write_text("\n".join(rewritten) + "\n")

    def park_item(self, question=HELD_QUESTION, dish="D1"):
        dish_args = ("--dish", dish) if dish else ()
        return self.brigade("86", "add", *dish_args, "--question", question,
                            "--options", "moved, keep parked", "--default", "keep parked")

    def store_bytes(self):
        return tuple((self.at / name).read_bytes() for name in ("86.tsv", "log.tsv", "restaurant.json"))

    def open_admin(self):
        return self.run_at(self.store / "bridge-kit" / ".admin", "open", "--admin", "--project-root", str(self.project))

    def admin(self, *args, ok=True):
        return self.run_at(self.store / "bridge-kit" / ".admin", *args, ok=ok)

    def landing_db(self):
        import sqlite3
        database = next((Path(self.temporary.name) / "state").glob("pstack-t3/landing/*/land.db"))
        db = sqlite3.connect(database)
        db.row_factory = sqlite3.Row
        return db

    def lease_row(self, number):
        from contextlib import closing
        with closing(self.landing_db()) as db:
            return dict(db.execute("SELECT * FROM lease WHERE id = ?", (number,)).fetchone())

    def seed_entry(self, sha, state, note):
        """A queue entry for perf/D1 at another commit whose first 12 characters match, copied from E1."""
        from contextlib import closing
        with closing(self.landing_db()) as db, db:
            db.execute("INSERT INTO entry (at, holder, branch, sha, base, fingerprint, lease, reviewer, state, note) "
                       "SELECT at, holder, branch, ?, base, fingerprint, lease, reviewer, ?, ? FROM entry WHERE id = 1",
                       (sha, state, note))

    @staticmethod
    def same_prefix(sha):
        return sha[:12] + ("1" if sha[12] == "0" else "0") + sha[13:]

    def worker_commit(self, branch, files):
        path = Path(self.temporary.name) / branch.replace("/", "-")
        git = lambda *command, cwd=self.project: subprocess.run(command, cwd=cwd, capture_output=True, text=True,
                                                                check=True).stdout.strip()
        if not path.exists():
            git("git", "worktree", "add", "-q", "-b", branch, str(path), "main")
        for name, text in files.items():
            if text is None:
                (path / name).unlink()
            else:
                (path / name).write_text(text)
        git("git", "add", "-A", cwd=path)
        git("git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", branch, cwd=path)
        return git("git", "rev-parse", "HEAD", cwd=path)

    def passed(self, sha):
        self.brigade("dish", "D1", "--state", "in-review", "--sha", sha)
        self.brigade("pass", "record", "D1", "--sha", sha, "--verdict", "pass", "--author", CODEX, "--verifier", CLAUDE)

    def submit(self, sha):
        return self.land("submit", "--holder", "perf/D1", "--branch", "perf/d1", "--sha", sha, "--lease", "L1",
                         "--reviewer", CLAUDE)

    def test_watch_renews_a_live_lease_and_records_activity(self):
        self.started()
        self.land("lease", "renew", "L1", "--ttl-hours", "0.01")
        before = json.loads((self.at / "restaurant.json").read_text())["lastActivityAt"]
        self.assertLess(self.lease_row(1)["expires"], (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat())
        self.assertEqual(self.brigade("watch"), "D1: running 0m of 60m (no worker recorded)")
        self.assertGreater(self.lease_row(1)["expires"], (datetime.now(timezone.utc) + timedelta(hours=5.9)).isoformat())
        self.assertGreater(json.loads((self.at / "restaurant.json").read_text())["lastActivityAt"], before)

    def test_an_expired_lease_stays_expired_until_an_explicit_renew(self):
        self.started()
        self.land("lease", "renew", "L1", "--ttl-hours", "0")
        expired = self.lease_row(1)["expires"]
        self.assertEqual(self.brigade("watch").splitlines(),
                         ["D1: running 0m of 60m (no worker recorded)",
                          "D1: lease L1 expired; stop its worker, then run lease renew L1"])
        self.assertEqual(self.lease_row(1)["expires"], expired)
        self.assertEqual(self.land("lease", "renew", "L1"), "L1 renewed")
        self.assertEqual(self.brigade("watch"), "D1: running 0m of 60m (no worker recorded)")

    def test_re_admitting_an_expired_lease_names_the_holder_that_claimed_its_paths(self):
        self.started()
        self.land("lease", "renew", "L1", "--ttl-hours", "0")
        self.assertEqual(self.land("lease", "claim", "--holder", "engine/D1", "--paths", "README.md"), "L2")
        self.assertIn("D1: lease L1 expired; stop its worker, then run lease renew L1", self.brigade("watch"))
        self.assertEqual(self.land("lease", "renew", "L1", ok=False),
                         "land: L1 expired and L2 held by engine/D1 now covers README.md; claim again after it is released")

    def test_a_released_or_unreadable_lease_gets_its_own_line(self):
        self.started()
        self.brigade("dish", "D1", "--state", "in-review", "--sha", "abc1234")
        self.land("lease", "release", "L1")
        self.assertEqual(self.brigade("watch"), "D1: lease L1 was released; claim again before submitting")
        before = (self.at / "restaurant.json").read_text()
        (Path(self.temporary.name) / "state").rename(Path(self.temporary.name) / "moved")
        self.assertEqual(self.brigade("watch"),
                         f"D1: could not renew L1: {self.project} has no landing contract; run land.py init in it")
        self.assertEqual((self.at / "restaurant.json").read_text(), before)

    def test_review_passed_parked_and_sent_back_items_each_get_a_watch_line_and_renew(self):
        self.started()
        verdict = ("pass", "record", "D1", "--sha", "abc1234", "--author", CODEX, "--verifier", CLAUDE, "--verdict")
        steps = [(("dish", "D1", "--state", "in-review", "--sha", "abc1234"), "D1: in review"),
                 ((*verdict, "send-back"), "D1: sent back"),
                 ((*verdict, "blocked"), "D1: parked"),
                 ((*verdict, "pass"), "D1: passed, not submitted")]
        for command, line in steps:
            self.brigade(*command)
            self.land("lease", "renew", "L1", "--ttl-hours", "0.01")
            self.assertEqual(self.brigade("watch"), line)
            self.assertGreater(self.lease_row(1)["expires"],
                               (datetime.now(timezone.utc) + timedelta(hours=5.9)).isoformat(), line)

    PENDING = "D1: 3 send-backs, decision pending"
    NO_FIX_ROUND = ("brigade: D1 has 3 send-backs; no fix round until its decision is answered; "
                    "run 86 add --dish D1 --round-budget")
    ROUND_QUESTION = ("D1 was sent back 3 times. Accept the remaining findings as known limits and land it, "
                      "send it through architect for a redesign, or drop it?")
    ROUND_BUDGET = ("86", "add", "--dish", "D1", "--round-budget")

    def send_back(self, sha, *extra):
        return self.brigade("pass", "record", "D1", "--sha", sha, "--verdict", "send-back",
                            "--author", CODEX, "--verifier", CLAUDE, *extra)

    def sent_back(self, rounds, start=1):
        for number in range(start, start + rounds):
            if number > start:
                self.assertEqual(self.brigade("dish", "D1", "--state", "in-progress"), "D1 in-progress")
            printed = self.send_back(f"a{number}")
        return printed

    def test_the_third_send_back_refuses_another_fix_round(self):
        self.started()
        self.assertEqual(self.sent_back(2), "D1 sent-back")
        self.assertEqual(self.brigade("watch"), "D1: sent back")
        self.brigade("dish", "D1", "--state", "in-progress")
        self.assertEqual(self.send_back("a3"), "D1 sent-back; 3 send-backs, decision pending")
        before = tuple((self.at / name).read_bytes() for name in ("dishes.tsv", "log.tsv", "86.tsv"))
        self.assertEqual(self.brigade("dish", "D1", "--state", "in-progress", ok=False), self.NO_FIX_ROUND)
        self.assertEqual(self.brigade("dish", "D1", "--state", "in-progress", "--thread", "w9", ok=False), self.NO_FIX_ROUND)
        self.assertEqual(tuple((self.at / name).read_bytes() for name in ("dishes.tsv", "log.tsv", "86.tsv")), before)
        self.assertEqual(self.brigade("watch"), self.PENDING)
        self.assertEqual(self.brigade("dish", "D1", "--state", "in-review", "--sha", "a3"), "D1 in-review")
        self.assertEqual(self.brigade("dish", "D1", "--state", "in-progress", ok=False), self.NO_FIX_ROUND)

    def test_86_add_round_budget_writes_the_three_option_decision(self):
        self.started()
        self.sent_back(2)
        self.brigade("dish", "D1", "--state", "in-progress")
        self.review_file("D1-review-3.md")
        self.send_back("a3", "--report", "D1-review-3.md")
        self.assertEqual(self.brigade(*self.ROUND_BUDGET), "Q1")
        row = self.table_row(self.at, "86.tsv", "Q1")
        self.assertEqual((row["state"], row["dish"], row["question"], row["options"], row["default"], row["kind"],
                          row["answered"]),
                         ("open", "D1", f"{self.ROUND_QUESTION} Findings: reports/D1-review-3.md.",
                          "known limits, redesign, drop, keep parked", "keep parked", "round-budget", ""))
        table = (self.at / "86.tsv").read_bytes()
        self.assertEqual(self.brigade(*self.ROUND_BUDGET), "Q1")
        self.assertEqual((self.at / "86.tsv").read_bytes(), table)
        self.assertEqual(self.brigade("watch").splitlines(), [
            self.PENDING,
            f"D1: open decision Q1: {self.ROUND_QUESTION} Findings: reports/D1-review-3.md.; "
            "launch no worker or verifier until 86 answer Q1",
        ])

    def test_86_add_round_budget_is_refused_below_three_send_backs(self):
        self.started()
        table = (self.at / "86.tsv").read_bytes()
        self.assertEqual(self.brigade(*self.ROUND_BUDGET, ok=False),
                         "brigade: D1 has 0 send-backs since its last pass or round decision; the decision opens at 3")
        self.sent_back(1)
        self.assertEqual(self.brigade(*self.ROUND_BUDGET, ok=False),
                         "brigade: D1 has 1 send-back since its last pass or round decision; the decision opens at 3")
        self.assertEqual(self.brigade("86", "add", "--dish", "D9", "--round-budget", ok=False), "brigade: no D9 in dishes.tsv")
        self.assertEqual((self.at / "86.tsv").read_bytes(), table)

    def test_86_add_takes_a_question_or_the_round_budget(self):
        self.started()
        self.sent_back(3)
        needs = "brigade: 86 add needs --question, --options, and --default"
        self.assertEqual(self.brigade("86", "add", ok=False), needs)
        self.assertEqual(self.brigade("86", "add", "--dish", "D1", "--question", "Move?", "--options", "a, b", ok=False), needs)
        alone = "brigade: 86 add --round-budget takes --dish and no --question, --options, or --default"
        self.assertEqual(self.brigade("86", "add", "--round-budget", ok=False), alone)
        self.assertEqual(self.brigade(*self.ROUND_BUDGET, "--question", "Move?", ok=False), alone)
        self.assertEqual(self.brigade(*self.ROUND_BUDGET, "--default", "drop", ok=False), alone)
        self.assertEqual((self.at / "86.tsv").read_text().splitlines(),
                         ["id\tat\tstate\tdish\tquestion\toptions\tdefault\tanswer\tkind\tanswered"])
        self.assertEqual(self.brigade("86", "add", "--question", "Ship it?", "--options", "yes, no", "--default", "no"), "Q1")
        self.assertEqual(self.park_item(), "Q2")

    def test_keep_parked_leaves_the_round_decision_open_and_the_refusal_in_place(self):
        self.started()
        self.sent_back(3)
        self.assertEqual(self.brigade(*self.ROUND_BUDGET), "Q1")
        self.assertEqual(self.table_row(self.at, "86.tsv", "Q1")["question"], self.ROUND_QUESTION)
        self.assertEqual(self.brigade("86", "answer", "Q1", "--answer", "keep parked"),
                         "Q1 still open; D1 stays held until 86 answer Q1 --answer 'known limits' or redesign or drop")
        self.assertEqual(self.brigade("dish", "D1", "--state", "in-progress", ok=False), self.NO_FIX_ROUND)
        self.assertEqual(self.brigade("watch").splitlines()[0], self.PENDING)

    def round_decision_lifts_the_refusal(self, answer, stored):
        self.started()
        self.sent_back(3)
        self.assertEqual(self.brigade(*self.ROUND_BUDGET), "Q1")
        self.assertEqual(self.brigade("86", "answer", "Q1", "--answer", answer), "Q1 answered")
        self.assertEqual(self.table_row(self.at, "86.tsv", "Q1")["answer"], stored)
        self.assertEqual(self.brigade("watch"), "D1: sent back")
        self.assertEqual(self.brigade(*self.ROUND_BUDGET, ok=False),
                         "brigade: D1 has 0 send-backs since its last pass or round decision; the decision opens at 3")
        self.assertEqual(self.brigade("dish", "D1", "--state", "in-progress"), "D1 in-progress")

    def test_known_limits_closes_the_round_decision_and_lifts_the_refusal(self):
        self.round_decision_lifts_the_refusal("Known limits.", "known limits")

    def test_redesign_closes_the_round_decision_and_lifts_the_refusal(self):
        self.round_decision_lifts_the_refusal("redesign", "redesign")

    def test_drop_closes_the_round_decision_and_lifts_the_refusal(self):
        self.round_decision_lifts_the_refusal("drop", "drop")

    def test_the_count_starts_again_after_a_round_decision(self):
        self.started()
        self.sent_back(3)
        self.brigade(*self.ROUND_BUDGET)
        self.brigade("86", "answer", "Q1", "--answer", "redesign")
        self.brigade("dish", "D1", "--state", "in-progress")
        self.assertEqual(self.sent_back(2, start=4), "D1 sent-back")
        self.assertEqual(self.brigade("dish", "D1", "--state", "in-progress"), "D1 in-progress")
        self.assertEqual(self.send_back("a6"), "D1 sent-back; 3 send-backs, decision pending")
        self.assertEqual(self.brigade("dish", "D1", "--state", "in-progress", ok=False), self.NO_FIX_ROUND)
        self.assertEqual(self.brigade("watch"), self.PENDING)
        self.assertEqual(self.brigade(*self.ROUND_BUDGET), "Q2")
        self.assertEqual(self.table_row(self.at, "86.tsv", "Q2")["question"], self.ROUND_QUESTION)

    PASS = ("pass", "record", "D1", "--verdict", "pass", "--author", CODEX, "--verifier", CLAUDE, "--sha")
    NO_DECISION = "brigade: D1 is {}; it owes no round decision"

    def test_a_pass_at_three_send_backs_settles_the_count(self):
        self.started()
        self.assertEqual(self.sent_back(3), "D1 sent-back; 3 send-backs, decision pending")
        self.assertEqual(self.brigade(*self.PASS, "a3"), "D1 passed")
        self.assertEqual(self.brigade("watch"), "D1: passed, not submitted")
        self.assertEqual(self.brigade(*self.FIX_BRIEF, ok=False),
                         "brigade: D1 is passed; brief a dish that is in progress or sent back")
        self.assertEqual(self.brigade(*self.ROUND_BUDGET, ok=False), self.NO_DECISION.format("passed"))
        self.assertEqual(self.brigade("dish", "D1", "--state", "queued"), "D1 queued")
        self.assertEqual(self.brigade(*self.ROUND_BUDGET, ok=False), self.NO_DECISION.format("queued"))
        self.assertEqual(self.brigade("dish", "D1", "--state", "in-progress", "--thread", "bounce-worker"), "D1 in-progress")
        self.assertEqual(self.brigade("watch"), "D1: running 0m of 60m (thread bounce-worker)")
        self.assertEqual(self.send_back("a4"), "D1 sent-back")
        self.assertEqual(self.brigade(*self.ROUND_BUDGET, ok=False),
                         "brigade: D1 has 1 send-back since its last pass or round decision; the decision opens at 3")
        self.assertEqual(self.brigade("86", "list"), "no open decisions")

    def test_a_merged_item_owes_nothing_and_its_ticket_starts_a_new_count(self):
        self.started()
        self.sent_back(3)
        self.assertEqual(self.brigade(*self.PASS, "a4"), "D1 passed")
        self.assertEqual(self.brigade("pass", "record", "D1", "--sha", "a4", "--verdict", "send-back", "--author", CODEX,
                                      "--verifier", CLAUDE, "--member"),
                         "D1: member send-back on record; D1 stays passed")
        self.assertEqual(self.brigade("dish", "D1", "--state", "merged"), "D1 merged")
        for sha in ("m1", "m2", "m3"):
            self.assertEqual(self.send_back(sha, "--late"), "D1: late send-back on record; D1 stays merged")
        self.assertEqual(self.brigade("watch"), "no work in progress")
        self.assertEqual(self.brigade(*self.ROUND_BUDGET, ok=False), self.NO_DECISION.format("merged"))
        self.assertEqual(self.brigade("ticket", "set", "T1", "--state", "waiting"), "T1 waiting")
        self.assertEqual(self.brigade(*self.FIRE_AGAIN), "D2")
        self.assertEqual(self.brigade("pass", "record", "D2", "--sha", "b1", "--verdict", "send-back", "--author", CODEX,
                                      "--verifier", CLAUDE), "D2 sent-back")
        self.assertEqual(self.brigade("watch"), "D2: sent back")
        self.assertEqual(self.brigade("86", "list"), "no open decisions")

    def test_a_dropped_item_owes_nothing_and_its_ticket_starts_a_new_count(self):
        self.started()
        self.sent_back(3)
        self.assertEqual(self.brigade("dish", "D1", "--state", "dropped"), "D1 dropped; T1 waiting again")
        self.assertEqual(self.brigade("watch"), "no work in progress")
        self.assertEqual(self.brigade(*self.ROUND_BUDGET, ok=False), self.NO_DECISION.format("dropped"))
        self.assertEqual(self.brigade(*self.FIRE_AGAIN), "D2")
        self.assertEqual(self.brigade("pass", "record", "D2", "--sha", "b1", "--verdict", "send-back", "--author", CODEX,
                                      "--verifier", CLAUDE), "D2 sent-back")
        self.assertEqual(self.brigade("watch"), "D2: sent back")
        self.assertEqual(self.brigade("86", "list"), "no open decisions")

    def test_a_dropped_item_put_back_in_progress_owes_its_decision_again(self):
        self.started()
        self.sent_back(3)
        self.brigade("dish", "D1", "--state", "dropped")
        self.assertEqual(self.brigade("dish", "D1", "--state", "in-progress"), "D1 in-progress")
        self.assertEqual(self.brigade("watch").splitlines()[0], self.PENDING)
        self.assertEqual(self.brigade("dish", "D1", "--thread", "fresh-worker", ok=False), self.NO_FIX_ROUND)
        self.assertEqual(self.brigade(*self.FIRE_AGAIN, ok=False), self.NO_FIRE)
        self.assertEqual(self.brigade(*self.ROUND_BUDGET), "Q1")

    def test_a_late_send_back_written_before_a_pass_stops_counting_at_the_pass(self):
        self.started()
        self.sent_back(2)
        self.brigade("dish", "D1", "--state", "in-progress")
        self.assertEqual(self.send_back("a0", "--late"),
                         "D1: late send-back on record; D1 stays in-progress; 3 send-backs, decision pending")
        self.passed("a3")
        self.assertEqual(self.brigade("watch"), "D1: passed, not submitted")
        self.brigade("dish", "D1", "--state", "queued")
        self.assertEqual(self.brigade("dish", "D1", "--state", "in-progress"), "D1 in-progress")
        self.assertEqual(self.send_back("a4"), "D1 sent-back")
        self.assertEqual(self.brigade(*self.ROUND_BUDGET, ok=False),
                         "brigade: D1 has 1 send-back since its last pass or round decision; the decision opens at 3")

    def test_late_send_backs_written_after_a_pass_count_once_the_item_is_back_in_progress(self):
        self.started()
        self.passed("a1")
        for sha in ("m1", "m2", "m3"):
            self.assertEqual(self.send_back(sha, "--late"), "D1: late send-back on record; D1 stays passed")
        self.assertEqual(self.brigade("watch"), "D1: passed, not submitted")
        self.assertEqual(self.brigade(*self.ROUND_BUDGET, ok=False), self.NO_DECISION.format("passed"))
        self.brigade("dish", "D1", "--state", "queued")
        self.assertEqual(self.brigade("dish", "D1", "--state", "in-progress"), "D1 in-progress")
        self.assertEqual(self.brigade("watch"), self.PENDING)
        self.assertEqual(self.brigade("dish", "D1", "--thread", "bounce-worker", ok=False), self.NO_FIX_ROUND)
        self.assertEqual(self.brigade(*self.ROUND_BUDGET), "Q1")
        self.assertEqual(self.brigade("86", "answer", "Q1", "--answer", "known limits"), "Q1 answered")
        self.assertEqual(self.brigade("dish", "D1", "--thread", "bounce-worker"), "D1 in-progress")

    def unchanged(self, before=None):
        now = tuple((self.at / name).read_bytes() for name in ("dishes.tsv", "rail.tsv", "log.tsv", "86.tsv"))
        if before is not None:
            self.assertEqual(now, before)
        return now

    def test_a_detour_through_review_starts_no_fix_round(self):
        self.started()
        self.sent_back(3)
        self.assertEqual(self.brigade("dish", "D1", "--state", "in-review"), "D1 in-review")
        self.assertEqual(self.brigade("watch"), self.PENDING)
        before = self.unchanged()
        self.assertEqual(self.brigade("dish", "D1", "--state", "in-progress", "--thread", "fresh-worker", ok=False),
                         self.NO_FIX_ROUND)
        self.assertEqual(self.brigade("dish", "D1", "--thread", "fresh-worker", ok=False), self.NO_FIX_ROUND)
        self.assertEqual(self.brigade("dish", "D1", "--task", "fresh-task", ok=False), self.NO_FIX_ROUND)
        self.unchanged(before)
        self.assertEqual(self.brigade("watch"), self.PENDING)
        self.assertEqual(self.brigade("86", "list"), "no open decisions")

    def test_watch_names_the_pending_decision_in_review_and_parked(self):
        self.started()
        self.sent_back(3)
        self.assertEqual(self.brigade("dish", "D1", "--state", "in-review"), "D1 in-review")
        self.assertEqual(self.brigade("watch"), self.PENDING)
        self.assertEqual(self.brigade("pass", "record", "D1", "--sha", "a3", "--verdict", "blocked", "--author", CODEX,
                                      "--verifier", CLAUDE), "D1 blocked")
        self.assertEqual(self.brigade("watch"), self.PENDING)

    def test_a_late_third_send_back_holds_an_item_in_progress(self):
        self.started()
        self.sent_back(2)
        self.brigade("dish", "D1", "--state", "in-progress", "--thread", "w3")
        self.assertEqual(self.brigade("watch"), "D1: running 0m of 60m (thread w3)")
        self.assertEqual(self.send_back("a0", "--late"),
                         "D1: late send-back on record; D1 stays in-progress; 3 send-backs, decision pending")
        self.assertEqual(self.brigade("watch"), self.PENDING)
        before = self.unchanged()
        self.assertEqual(self.brigade("dish", "D1", "--thread", "fresh-worker", ok=False), self.NO_FIX_ROUND)
        self.assertEqual(self.brigade("dish", "D1", "--task", "fresh-task", ok=False), self.NO_FIX_ROUND)
        self.assertEqual(self.brigade("dish", "D1", "--state", "in-progress", ok=False), self.NO_FIX_ROUND)
        self.unchanged(before)
        self.assertEqual(self.brigade("dish", "D1", "--thread", "w3", "--reported"), "D1 in-progress")
        self.assertEqual(self.brigade("dish", "D1", "--state", "in-review", "--sha", "a3"), "D1 in-review")
        self.assertEqual(self.brigade("watch"), self.PENDING)

    def test_a_late_send_back_below_the_budget_names_no_decision(self):
        self.started()
        self.sent_back(1)
        self.brigade("dish", "D1", "--state", "in-progress")
        self.assertEqual(self.send_back("a0", "--late"), "D1: late send-back on record; D1 stays in-progress")
        self.assertEqual(self.brigade("watch"), "D1: in progress with no worker thread; launch a fresh worker")
        self.assertEqual(self.brigade("dish", "D1", "--thread", "w2"), "D1 in-progress")

    FIRE_AGAIN = ("fire", "--tickets", "T1", "--station", "bug-fix", "--summary", "Fourth fix", "--thread", "fresh-worker")
    NO_FIRE = ("brigade: T1 is D1's ticket; D1 has 3 send-backs; no fix round until its decision is answered; "
               "run 86 add --dish D1 --round-budget")

    def test_fire_refuses_a_ticket_of_an_item_that_owes_its_decision(self):
        self.started()
        self.sent_back(3)
        self.assertEqual(self.brigade(*self.FIRE_AGAIN, ok=False), self.NO_FIRE)
        self.assertEqual(self.brigade("ticket", "set", "T1", "--state", "waiting"), "T1 waiting")
        before = self.unchanged()
        self.assertEqual(self.brigade(*self.FIRE_AGAIN, ok=False), self.NO_FIRE)
        self.unchanged(before)
        self.assertEqual(self.brigade("ticket", "list"), "T1 waiting [user] one")
        self.assertEqual(self.brigade(*self.ROUND_BUDGET), "Q1")
        self.assertEqual(self.brigade(*self.FIRE_AGAIN, ok=False), self.NO_FIRE)
        self.assertEqual(self.brigade("86", "answer", "Q1", "--answer", "redesign"), "Q1 answered")
        self.assertEqual(self.brigade(*self.FIRE_AGAIN), "D2")

    def test_fire_takes_the_ticket_of_an_item_under_its_budget(self):
        self.started()
        self.sent_back(2)
        self.assertEqual(self.brigade("dish", "D1", "--state", "dropped"), "D1 dropped; T1 waiting again")
        self.assertEqual(self.brigade(*self.FIRE_AGAIN), "D2")

    FIX_BRIEF = ("brief", "D1", "--goal", "g", "--acceptance", "a", "--verify", "v", "--base", "origin/main")

    def test_brief_refuses_an_item_that_owes_its_decision(self):
        self.started()
        self.brigade("set", "--thread", "c1")
        self.sent_back(2)
        self.assertIn("GOAL: g\n", self.brigade(*self.FIX_BRIEF))
        self.brigade("dish", "D1", "--state", "in-progress")
        self.send_back("a3")
        written = (self.at / "briefs" / "D1.md").read_bytes()
        before = self.unchanged()
        self.assertEqual(self.brigade(*self.FIX_BRIEF, ok=False), self.NO_FIX_ROUND)
        self.assertEqual(self.brigade("brief", "D1", "--goal", "g", "--verify", "v", "--base", "origin/main", ok=False),
                         self.NO_FIX_ROUND)
        self.unchanged(before)
        self.brigade("dish", "D1", "--state", "in-review")
        self.assertEqual(self.brigade(*self.FIX_BRIEF, ok=False), self.NO_FIX_ROUND)
        self.assertEqual((self.at / "briefs" / "D1.md").read_bytes(), written)
        self.brigade(*self.ROUND_BUDGET)
        self.brigade("86", "answer", "Q1", "--answer", "redesign")
        self.brigade("dish", "D1", "--state", "in-progress")
        self.assertIn("GOAL: g\n", self.brigade(*self.FIX_BRIEF))

    def test_an_ordinary_decision_answered_with_a_round_option_lifts_no_refusal(self):
        self.started()
        self.sent_back(3)
        self.assertEqual(self.brigade("86", "add", "--dish", "D1", "--question", "Redesign the title wording?",
                                      "--options", "redesign, keep parked", "--default", "keep parked"), "Q1")
        held = "brigade: D1 is held by Q1; answer it, then run 86 add --dish D1 --round-budget"
        table = (self.at / "86.tsv").read_bytes()
        self.assertEqual(self.brigade(*self.ROUND_BUDGET, ok=False), held)
        self.assertEqual((self.at / "86.tsv").read_bytes(), table)
        self.assertEqual(self.brigade("86", "answer", "Q1", "--answer", "redesign"), "Q1 answered")
        self.assertEqual(self.table_row(self.at, "86.tsv", "Q1")["kind"], "")
        self.assertEqual(self.brigade("dish", "D1", "--state", "in-progress", ok=False), self.NO_FIX_ROUND)
        self.assertEqual(self.brigade("watch"), self.PENDING)
        self.assertEqual(self.brigade(*self.ROUND_BUDGET), "Q2")
        self.assertEqual(self.table_row(self.at, "86.tsv", "Q2")["kind"], "round-budget")
        self.assertEqual(self.brigade("86", "answer", "Q2", "--answer", "redesign"), "Q2 answered")
        self.assertEqual(self.brigade("dish", "D1", "--state", "in-progress"), "D1 in-progress")

    def test_late_rows_recorded_while_the_decision_is_open_stop_counting_at_its_answer(self):
        self.started()
        self.sent_back(3)
        self.assertEqual(self.brigade(*self.ROUND_BUDGET), "Q1")
        for count in (4, 5, 6):
            self.assertEqual(self.send_back(f"missed{count}", "--late"),
                             f"D1: late send-back on record; D1 stays sent-back; {count} send-backs, decision pending")
        self.assertEqual(self.brigade("86", "answer", "Q1", "--answer", "redesign"), "Q1 answered")
        row = self.table_row(self.at, "86.tsv", "Q1")
        self.assertGreater(row["answered"], self.pass_rows()[-1][0])
        self.assertGreater(row["answered"], row["at"])
        self.assertEqual(self.brigade("watch"), "D1: sent back")
        self.assertEqual(self.brigade("dish", "D1", "--state", "in-progress"), "D1 in-progress")
        self.assertEqual(self.send_back("missed7", "--late"), "D1: late send-back on record; D1 stays in-progress")
        self.assertEqual(self.brigade(*self.ROUND_BUDGET, ok=False),
                         "brigade: D1 has 1 send-back since its last pass or round decision; the decision opens at 3")

    def test_a_decision_table_written_before_the_kind_and_answered_columns_still_reads(self):
        self.started()
        self.assertEqual(self.sent_back(3), "D1 sent-back; 3 send-backs, decision pending")
        stamp = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        old = ["\t".join(["Q1", stamp, "answered", "D1", "Drop this item?", "drop, keep parked", "keep parked", "drop"]),
               "\t".join(["Q2", stamp, "open", "", "Ship it?", "yes, no", "no", ""])]
        table = self.at / "86.tsv"
        table.write_text("id\tat\tstate\tdish\tquestion\toptions\tdefault\tanswer\n" + "\n".join(old) + "\n")
        self.assertEqual(self.brigade("86", "list"), "Q2: Ship it? Options: yes, no. Default: no.")
        self.assertEqual(self.brigade("dish", "D1", "--state", "in-progress", ok=False), self.NO_FIX_ROUND)
        self.assertEqual(self.brigade(*self.ROUND_BUDGET), "Q3")
        lines = table.read_text().splitlines()
        self.assertEqual(lines[1:3], old)
        self.assertEqual(lines[3].split("\t")[5:], ["known limits, redesign, drop, keep parked", "keep parked", "",
                                                     "round-budget", ""])
        self.assertEqual(self.brigade("86", "answer", "Q3", "--answer", "drop"), "Q3 answered")
        self.assertEqual(self.brigade("dish", "D1", "--state", "in-progress"), "D1 in-progress")
        stored = [self.table_row(self.at, "86.tsv", ident) for ident in ("Q1", "Q2", "Q3")]
        self.assertEqual([(row["state"], row["answer"], row["kind"], bool(row["answered"])) for row in stored],
                         [("answered", "drop", "", False), ("open", "", "", False), ("answered", "drop", "round-budget", True)])
        for fields, line in ((old[1].split("\t")[:7], 5), ([*old[1].split("\t"), "", "", "extra"], 5)):
            table.write_text(table.read_text() + "\t".join(fields) + "\n")
            self.assertEqual(self.brigade("86", "list", ok=False),
                             f"brigade: 86.tsv line {line} is malformed; fix or remove it")
            table.write_text("\n".join(table.read_text().splitlines()[:-1]) + "\n")

    def test_an_unrelated_answered_item_decision_lifts_no_refusal(self):
        self.started()
        self.sent_back(3)
        self.assertEqual(self.park_item(), "Q1")
        self.assertEqual(self.brigade("86", "answer", "Q1", "--answer", "moved"), "Q1 answered")
        self.assertNotEqual(self.table_row(self.at, "86.tsv", "Q1")["answered"], "")
        self.assertEqual(self.brigade("dish", "D1", "--state", "in-progress", ok=False), self.NO_FIX_ROUND)
        self.assertEqual(self.brigade("watch"), self.PENDING)
        self.assertEqual(self.brigade(*self.ROUND_BUDGET), "Q2")

    def test_member_send_backs_do_not_count_toward_the_round_budget(self):
        self.started()
        self.sent_back(2)
        for seat in ("grok/grok-4.7", "opencode/kimi-k3"):
            self.assertEqual(self.brigade("pass", "record", "D1", "--sha", "a2", "--verdict", "send-back", "--author", CODEX,
                                          "--verifier", seat, "--member"),
                             "D1: member send-back on record; D1 stays sent-back")
        self.assertEqual(self.brigade("watch"), "D1: sent back")
        self.assertEqual(self.brigade(*self.ROUND_BUDGET, ok=False),
                         "brigade: D1 has 2 send-backs since its last pass or round decision; the decision opens at 3")
        self.assertEqual(self.brigade("dish", "D1", "--state", "in-progress"), "D1 in-progress")

    def test_an_open_item_decision_replaces_an_over_timebox_line_and_renews_the_lease(self):
        self.started()
        self.brigade("dish", "D1", "--timebox", "30")
        self.backdate_attempt(45)
        self.land("lease", "renew", "L1", "--ttl-hours", "0.01")
        self.assertLess(self.lease_row(1)["expires"], (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat())
        self.assertEqual(self.park_item(), "Q1")
        before = json.loads((self.at / "restaurant.json").read_text())["lastActivityAt"]
        self.assertEqual(self.brigade("watch"), HELD_LINE)
        self.assertGreater(self.lease_row(1)["expires"],
                           (datetime.now(timezone.utc) + timedelta(hours=5.9)).isoformat())
        self.assertGreater(json.loads((self.at / "restaurant.json").read_text())["lastActivityAt"], before)

    def test_an_open_item_decision_replaces_the_no_worker_line(self):
        self.started()
        self.assertEqual(self.park_item(), "Q1")
        self.brigade("dish", "D1", "--state", "sent-back")
        self.brigade("dish", "D1", "--state", "in-progress")
        self.assertEqual(self.brigade("watch"), HELD_LINE)

    def test_an_open_item_decision_replaces_the_in_review_line(self):
        self.started()
        self.assertEqual(self.park_item(), "Q1")
        self.brigade("dish", "D1", "--state", "in-review", "--sha", "abc1234")
        self.assertEqual(self.brigade("watch"), HELD_LINE)

    def test_an_expired_lease_under_a_held_item_follows_the_decision_line(self):
        self.started()
        self.assertEqual(self.park_item(), "Q1")
        self.land("lease", "renew", "L1", "--ttl-hours", "0")
        self.assertEqual(self.brigade("watch").splitlines(), [
            HELD_LINE,
            "D1: lease L1 expired; stop its worker, then run lease renew L1",
        ])

    def test_answering_an_item_decision_restores_the_over_timebox_line(self):
        self.started()
        self.brigade("dish", "D1", "--timebox", "30")
        self.backdate_attempt(45)
        self.park_item()
        self.assertEqual(self.brigade("watch"), HELD_LINE)
        self.assertEqual(self.brigade("86", "answer", "Q1", "--answer", "moved"), "Q1 answered")
        self.assertRegex(
            self.brigade("watch"),
            r"^D1: over its 30m timebox at \d+m with no report; read its thread and decide \(no worker recorded\)$",
        )

    def test_answering_an_item_decision_restores_the_no_worker_line(self):
        self.started()
        self.park_item()
        self.brigade("dish", "D1", "--state", "sent-back")
        self.brigade("dish", "D1", "--state", "in-progress")
        self.assertEqual(self.brigade("watch"), HELD_LINE)
        self.assertEqual(self.brigade("86", "answer", "Q1", "--answer", "moved"), "Q1 answered")
        self.assertEqual(self.brigade("watch"), "D1: in progress with no worker thread; launch a fresh worker")

    def test_answering_an_item_decision_restores_the_in_review_line(self):
        self.started()
        self.park_item()
        self.brigade("dish", "D1", "--state", "in-review", "--sha", "abc1234")
        self.assertEqual(self.brigade("watch"), HELD_LINE)
        self.assertEqual(self.brigade("86", "answer", "Q1", "--answer", "moved"), "Q1 answered")
        self.assertEqual(self.brigade("watch"), "D1: in review")

    def test_86_list_names_the_item_and_keeps_a_blank_dish_in_the_old_format(self):
        self.started()
        self.assertEqual(self.park_item(), "Q1")
        self.assertEqual(self.brigade("86", "add", "--question", "Ship it?", "--options", "yes, no", "--default", "no"), "Q2")
        self.assertEqual(self.brigade("86", "list"), "\n".join([
            f"Q1 for D1: {HELD_QUESTION} Options: moved, keep parked. Default: keep parked.",
            "Q2: Ship it? Options: yes, no. Default: no.",
        ]))

    def test_a_blank_dish_decision_does_not_hold_the_item(self):
        self.started()
        self.brigade("dish", "D1", "--state", "in-review", "--sha", "abc1234")
        self.assertEqual(self.brigade("86", "add", "--question", "Ship it?", "--options", "yes, no", "--default", "no"), "Q1")
        self.assertEqual(self.brigade("86", "list"), "Q1: Ship it? Options: yes, no. Default: no.")
        self.assertEqual(self.brigade("watch"), "D1: in review")

    def test_a_second_86_add_for_a_held_item_prints_the_open_id_and_appends_nothing(self):
        self.started()
        self.assertEqual(self.park_item(), "Q1")
        table = (self.at / "86.tsv").read_text()
        decisions = [row for row in self.log_rows() if row["kind"] == "decision"]
        self.assertEqual(len(decisions), 1)
        self.assertEqual(len([line for line in table.splitlines() if line]) - 1, 1)
        other = "D1: cursor could not pass the seat's options: refused again. Move this coordinator to a provider that passes them?"
        self.assertEqual(self.park_item(other), "Q1")
        self.assertEqual((self.at / "86.tsv").read_text(), table)
        self.assertEqual([row for row in self.log_rows() if row["kind"] == "decision"], decisions)
        self.assertEqual(self.brigade("watch"), HELD_LINE)
        self.assertEqual(self.brigade("watch"), HELD_LINE)

    def test_keep_parked_leaves_the_item_decision_open_and_writes_nothing(self):
        self.started()
        self.assertEqual(self.park_item(), "Q1")
        before = self.store_bytes()
        self.assertEqual(self.brigade("86", "answer", "Q1", "--answer", "keep parked"), STILL_OPEN)
        self.assertEqual(self.store_bytes(), before)
        self.assertEqual(self.brigade("watch"), HELD_LINE)

    def test_a_relayed_keep_parked_leaves_the_item_held(self):
        self.started()
        self.assertEqual(self.park_item(), "Q1")
        self.open_admin()
        before = (self.at / "86.tsv").read_bytes()
        self.admin("request", "--to", "perf", "answer perf Q1: keep parked")
        self.assertEqual(self.brigade("inbox", "take"), "A1: answer perf Q1: keep parked")
        self.assertEqual(self.brigade("86", "answer", "Q1", "--answer", "keep parked"), STILL_OPEN)
        self.assertEqual(self.brigade("inbox", "done", "A1"), "A1 done")
        self.assertEqual(self.brigade("watch"), HELD_LINE)
        self.assertEqual((self.at / "86.tsv").read_bytes(), before)

    def test_a_replayed_keep_parked_relay_logs_inbox_done_once(self):
        self.started()
        self.assertEqual(self.park_item(), "Q1")
        self.open_admin()
        before = (self.at / "86.tsv").read_bytes()
        self.admin("request", "--to", "perf", "answer perf Q1: keep parked")
        self.assertEqual(self.brigade("inbox", "take"), "A1: answer perf Q1: keep parked")
        self.assertEqual(self.brigade("86", "answer", "Q1", "--answer", "keep parked"), STILL_OPEN)
        self.assertEqual(self.brigade("inbox", "take"), "A1: answer perf Q1: keep parked")
        self.assertEqual(self.brigade("86", "answer", "Q1", "--answer", "keep parked"), STILL_OPEN)
        self.assertEqual(self.brigade("inbox", "done", "A1"), "A1 done")
        self.assertEqual(self.brigade("inbox", "take"), "nothing handed to you")
        self.assertEqual(self.brigade("inbox", "done", "A1"), "A1 done")
        self.assertEqual((self.at / "86.tsv").read_bytes(), before)
        done = [row for row in self.log_rows() if row["kind"] == "inbox-done"]
        self.assertEqual([(row["id"], row["state"], row["note"]) for row in done],
                         [("A1", "done", "answer perf Q1: keep parked")])

    def test_moved_closes_an_item_decision_and_a_later_answer_writes_nothing(self):
        self.started()
        ordinary = self.brigade("watch")
        self.assertEqual(ordinary, "D1: running 0m of 60m (no worker recorded)")
        self.park_item()
        opened = [row for row in self.log_rows() if row["kind"] == "decision"]
        self.assertEqual(self.brigade("86", "answer", "Q1", "--answer", "Moved."), "Q1 answered")
        row = self.table_row(self.at, "86.tsv", "Q1")
        self.assertEqual((row["state"], row["answer"]), ("answered", "moved"))
        answered = [row for row in self.log_rows() if row["kind"] == "decision" and row["state"] == "answered"]
        self.assertEqual(len(answered), 1)
        self.assertEqual(len([row for row in self.log_rows() if row["kind"] == "decision"]), len(opened) + 1)
        self.assertEqual(self.brigade("watch"), ordinary)
        before = self.store_bytes()
        self.assertEqual(self.brigade("86", "answer", "Q1", "--answer", "keep parked"), "Q1 answered")
        self.assertEqual(self.store_bytes(), before)

    def test_a_second_refusal_after_keep_parked_prints_the_open_id(self):
        self.started()
        self.assertEqual(self.park_item(), "Q1")
        self.assertEqual(self.brigade("86", "answer", "Q1", "--answer", "keep parked"), STILL_OPEN)
        table = (self.at / "86.tsv").read_text()
        decisions = [row for row in self.log_rows() if row["kind"] == "decision"]
        other = "D1: cursor could not pass the seat's options: refused again. Move this coordinator to a provider that passes them?"
        self.assertEqual(self.park_item(other), "Q1")
        self.assertEqual((self.at / "86.tsv").read_text(), table)
        self.assertEqual([row for row in self.log_rows() if row["kind"] == "decision"], decisions)

    def test_free_text_keeps_the_hold_and_writes_nothing(self):
        self.started()
        self.assertEqual(self.park_item(), "Q1")
        before = self.store_bytes()
        self.assertEqual(self.brigade("86", "answer", "Q1", "--answer", "I moved it"), STILL_OPEN)
        self.assertEqual(self.store_bytes(), before)
        self.assertEqual(self.brigade("watch"), HELD_LINE)

    def test_an_item_decision_needs_a_default_and_a_closing_option(self):
        self.started()
        self.assertEqual(self.brigade("86", "add", "--dish", "D1", "--question", "Move?",
                                      "--options", "keep parked", "--default", "keep parked", ok=False), ITEM_DECISION)
        self.assertEqual(self.brigade("86", "add", "--dish", "D1", "--question", "Move?",
                                      "--options", "moved, keep parked", "--default", "ship it", ok=False), ITEM_DECISION)
        self.assertEqual((self.at / "86.tsv").read_text().splitlines(),
                         ["id\tat\tstate\tdish\tquestion\toptions\tdefault\tanswer\tkind\tanswered"])
        self.assertEqual(self.park_item(), "Q1")
        table = (self.at / "86.tsv").read_text()
        self.assertEqual(self.brigade("86", "add", "--dish", "D1", "--question", "Move?",
                                      "--options", "keep parked", "--default", "keep parked"), "Q1")
        self.assertEqual(self.brigade("86", "add", "--dish", "D1", "--question", "Move?",
                                      "--options", "moved, keep parked", "--default", "ship it"), "Q1")
        self.assertEqual((self.at / "86.tsv").read_text(), table)

    def test_an_item_decision_whose_options_collapse_to_the_default_once_stored_is_refused(self):
        self.started()
        before = tuple((self.at / name).read_bytes() for name in ("86.tsv", "log.tsv"))
        for options in ("keep parked, keep\nparked", "keep parked, keep\tparked", "keep parked, keep\r\nparked"):
            self.assertEqual(self.brigade("86", "add", "--dish", "D1", "--question", "Move?",
                                          "--options", options, "--default", "keep parked", ok=False),
                             ITEM_DECISION, repr(options))
            self.assertEqual(tuple((self.at / name).read_bytes() for name in ("86.tsv", "log.tsv")), before,
                             repr(options))

    def test_an_item_decision_stores_its_options_cleaned_and_closes_only_on_the_other_option(self):
        self.started()
        self.assertEqual(self.brigade("86", "add", "--dish", "D1", "--question", "Move\tthis?",
                                      "--options", "moved\r\nelsewhere, keep\nparked",
                                      "--default", "keep\tparked"), "Q1")
        row = self.table_row(self.at, "86.tsv", "Q1")
        self.assertEqual((row["question"], row["options"], row["default"]),
                         ("Move this?", "moved elsewhere, keep parked", "keep parked"))
        before = self.store_bytes()
        self.assertEqual(self.brigade("86", "answer", "Q1", "--answer", "keep parked"),
                         "Q1 still open; D1 stays held until 86 answer Q1 --answer 'moved elsewhere'")
        self.assertEqual(self.store_bytes(), before)
        self.assertEqual(self.brigade("86", "answer", "Q1", "--answer", "Moved elsewhere."), "Q1 answered")
        row = self.table_row(self.at, "86.tsv", "Q1")
        self.assertEqual((row["state"], row["answer"]), ("answered", "moved elsewhere"))

    def test_a_blank_dish_decision_still_closes_on_any_text(self):
        self.started()
        self.brigade("dish", "D1", "--state", "in-review", "--sha", "abc1234")
        self.assertEqual(self.brigade("86", "add", "--question", "Ship it?",
                                      "--options", "keep parked", "--default", "keep parked"), "Q1")
        self.assertEqual(self.brigade("86", "answer", "Q1", "--answer", "keep parked"), "Q1 answered")
        row = self.table_row(self.at, "86.tsv", "Q1")
        self.assertEqual((row["state"], row["answer"]), ("answered", "keep parked"))
        self.assertEqual(self.brigade("86", "add", "--question", "Really?",
                                      "--options", "yes", "--default", "no"), "Q2")
        self.assertEqual(self.brigade("86", "answer", "Q2", "--answer", "whatever"), "Q2 answered")
        self.assertEqual(self.table_row(self.at, "86.tsv", "Q2")["answer"], "whatever")
        self.assertEqual(self.brigade("watch"), "D1: in review")

    def test_a_legacy_item_row_with_no_closing_option_closes_on_any_answer(self):
        self.started()
        ordinary = self.brigade("watch")
        question = "Hold this item?"
        path = self.at / "86.tsv"
        header = path.read_text().splitlines()[0]
        row = "\t".join(["Q1", "2026-10-06T00:00:00+00:00", "open", "D1", question, "keep parked", "keep parked", ""])
        path.write_text(header + "\n" + row + "\n")
        self.assertEqual(
            self.brigade("watch"),
            f"D1: open decision Q1: {question}; launch no worker or verifier until 86 answer Q1",
        )
        self.assertEqual(self.brigade("86", "answer", "Q1", "--answer", "keep parked"), "Q1 answered")
        stored = self.table_row(self.at, "86.tsv", "Q1")
        self.assertEqual((stored["state"], stored["answer"]), ("answered", "keep parked"))
        self.assertEqual(self.brigade("watch"), ordinary)

    def test_a_passed_item_with_a_submitted_entry_says_mark_it_queued(self):
        self.started()
        sha = self.worker_commit("perf/d1", {"README.md": "fast\n"})
        self.passed(sha)
        self.assertEqual(self.submit(sha), "E1")
        self.assertEqual(self.brigade("watch"), "D1: E1 already submitted; mark it queued")

    def test_a_passed_item_whose_entry_landed_is_not_told_to_claim_again(self):
        self.started()
        sha = self.worker_commit("perf/d1", {"README.md": "fast\n"})
        self.passed(sha)
        self.submit(sha)
        self.land("land")
        self.assertEqual(self.brigade("watch"), "D1: E1 already submitted; mark it queued")

    def test_dropping_a_queued_item_whose_entry_bounced_releases_its_lease(self):
        self.started("--check", "test ! -e BROKEN", paths="README.md,BROKEN")
        self.brigade("dish", "D1", "--thread", "w1")
        sha = self.worker_commit("perf/d1", {"BROKEN": "x\n"})
        self.passed(sha)
        self.submit(sha)
        self.brigade("dish", "D1", "--state", "queued")
        self.land("land")
        self.assertIn("D1 holds L1", self.brigade("dish", "D1", "--state", "dropped", ok=False))
        self.assertEqual(self.brigade("dish", "D1", "--state", "dropped", "--stopped", "idle"), "D1 dropped; T1 waiting again")
        self.assertEqual(self.land("lease", "list"), "no leases held")

    def test_an_entry_another_run_landed_says_mark_it_merged(self):
        self.started()
        sha = self.worker_commit("perf/d1", {"README.md": "fast\n"})
        self.passed(sha)
        self.submit(sha)
        self.brigade("dish", "D1", "--state", "queued")
        self.assertEqual(self.brigade("watch"), "D1: E1 queued")
        self.land("land")
        landed = subprocess.run(["git", "rev-parse", "refs/landing/lane"], cwd=self.project, capture_output=True,
                                text=True, check=True).stdout.strip()
        self.assertEqual(self.brigade("watch"), f"D1: landed as E1 ({landed[:12]}); mark it merged")

    def test_an_old_bounced_entry_is_ignored_for_the_current_sha(self):
        self.started("--check", "test ! -e BROKEN", paths="README.md,BROKEN")
        old = self.worker_commit("perf/d1", {"README.md": "fast\n", "BROKEN": "x\n"})
        self.passed(old)
        self.submit(old)
        self.brigade("dish", "D1", "--state", "queued")
        self.land("land")
        self.assertRegex(self.brigade("watch"), r"^D1: E1 bounced: checks failed")
        self.brigade("dish", "D1", "--thread", "worker-1")
        self.brigade("dish", "D1", "--state", "in-progress")
        self.assertEqual(self.table_row(self.at, "dishes.tsv", "D1")["thread"], "")
        self.assertIn("D1: in progress with no worker thread; launch a fresh worker", self.brigade("watch"))
        self.assertEqual(self.brigade("dish", "D1", "--thread", "worker-1", ok=False),
                         "brigade: thread worker-1 is an earlier attempt of D1; a send-back launches a fresh worker")
        self.brigade("dish", "D1", "--thread", "worker-2")
        new = self.worker_commit("perf/d1", {"BROKEN": None})
        self.passed(new)
        self.assertEqual(self.submit(new), "E2")
        self.brigade("dish", "D1", "--state", "queued")
        self.assertEqual(self.brigade("watch"), "D1: E2 queued")

    def test_an_old_bounce_at_a_sha_sharing_the_items_prefix_is_ignored(self):
        self.started()
        sha = self.worker_commit("perf/d1", {"README.md": "reviewed\n"})
        self.passed(sha)
        self.submit(sha)
        from contextlib import closing
        with closing(self.landing_db()) as db, db:
            db.execute("UPDATE entry SET sha = ?, state = 'bounced', note = 'old different SHA' WHERE id = 1",
                       (self.same_prefix(sha),))
            db.execute("UPDATE lease SET state = 'active' WHERE id = 1")
        self.assertEqual(self.brigade("watch"), "D1: passed, not submitted")

    def test_a_later_bounce_sharing_the_prefix_does_not_hide_the_queued_entry(self):
        self.started()
        sha = self.worker_commit("perf/d1", {"README.md": "reviewed\n"})
        self.passed(sha)
        self.assertEqual(self.submit(sha), "E1")
        self.brigade("dish", "D1", "--state", "queued")
        self.seed_entry(self.same_prefix(sha), "bounced", "other SHA")
        self.assertEqual(self.land("status", "--holder", "perf/D1").splitlines()[1],
                         f"E2 bounced (perf/D1, {sha[:12]}): other SHA")
        self.assertEqual(self.brigade("watch"), "D1: E1 queued")

    def test_a_drop_waits_for_the_worker_and_then_releases_the_lease(self):
        self.started()
        self.brigade("dish", "D1", "--thread", "w1")
        self.assertEqual(self.brigade("dish", "D1", "--state", "dropped", ok=False),
                         "brigade: D1 holds L1 and its worker may still be running; "
                         "wait for its run with t3_thread_wait, then pass --stopped <run id>")
        self.assertEqual(self.table_row(self.at, "dishes.tsv", "D1")["state"], "in-progress")
        self.assertEqual(self.land("lease", "list").split(" until ")[0], "L1 active perf/D1")
        self.assertIn("L1 held by perf/D1",
                      self.land("lease", "claim", "--holder", "engine/D1", "--paths", "README.md", ok=False))
        self.worker_commit("perf/d1", {"README.md": "late\n"})
        self.assertEqual(self.brigade("dish", "D1", "--state", "dropped", "--stopped", "r1"), "D1 dropped; T1 waiting again")
        dropped = [line for line in (self.at / "log.tsv").read_text().splitlines() if "\tD1\tdropped\t" in line]
        self.assertEqual(len(dropped), 1)
        self.assertIn("stopped r1", dropped[0])
        self.assertEqual(self.land("lease", "claim", "--holder", "engine/D1", "--paths", "README.md"), "L2")

    def test_a_late_worker_submit_after_the_drop_is_refused(self):
        self.started()
        self.brigade("dish", "D1", "--thread", "w1")
        self.worker_commit("perf/d1", {"README.md": "first\n"})
        case = Path(self.temporary.name)
        worktree = case / "perf-d1"
        script = (f"while [ ! -e {shlex.quote(str(case / 'go'))} ]; do sleep 0.01; done; "
                  f"echo late > README.md && git add -A && git -c user.name=t -c user.email=t@t commit -qm late && "
                  f"{shlex.quote(sys.executable)} {shlex.quote(str(ROOT / 't3/added/landing/scripts/land.py'))} "
                  f"--repo {shlex.quote(str(self.project))} submit --holder perf/D1 --branch perf/d1 "
                  f"--sha $(git rev-parse HEAD) --lease L1 --reviewer {CLAUDE}")
        worker = subprocess.Popen(["bash", "-c", script], cwd=worktree, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True)
        try:
            self.assertEqual(self.brigade("dish", "D1", "--state", "dropped", "--stopped", "r1"), "D1 dropped; T1 waiting again")
            engine = self.store / "bridge-kit" / "engine"
            self.run_at(engine, "open", "--project-root", str(self.project), "--name", "Engine")
            (engine / "menu.md").write_text("## Purpose\n\nEngine.\n")
            self.run_at(engine, "ticket", "add", "--summary", "engine work")
            self.assertEqual(self.run_at(engine, "fire", "--tickets", "T1", "--station", "bug-fix", "--summary", "e",
                                         "--paths", "README.md"), "D1 (lease L2 held by engine/D1)")
            (case / "go").touch()
            _, err = worker.communicate(timeout=30)
        finally:
            worker.kill()
        self.assertEqual(worker.returncode, 1)
        self.assertEqual(err.strip(), "land: L1 is not an active lease held by perf/D1; claim one before submitting")
        self.assertEqual(self.land("status", "--holder", "perf/D1"), "no entries held by perf/D1")
        self.assertEqual([line.split(" until ")[0] for line in self.land("lease", "list").splitlines()],
                         ["L2 active engine/D1"])
        self.assertEqual(self.table_row(engine, "dishes.tsv", "D1")["lease"], "L2")

    def test_a_replaced_coordinators_paused_commands_change_nothing(self):
        self.init_landing()
        self.landing_env()
        docs = self.store / "bridge-kit" / "docs"
        self.run_at(docs, "open", "--project-root", str(self.project), "--name", "Docs")
        (docs / "menu.md").write_text("## Purpose\n\nDocs.\n")
        self.run_at(docs, "set", "--thread", "t1")
        old = ("--owner", "t1@1")
        self.assertIn("owner t1@1", self.run_at(docs, *old, "status"))
        self.run_at(docs, *old, "ticket", "add", "--summary", "one")
        self.assertEqual(self.run_at(docs, *old, "fire", "--tickets", "T1", "--station", "bug-fix", "--summary", "s",
                                     "--paths", "README.md"), "D1 (lease L1 held by docs/D1)")
        self.run_at(docs, *old, "dish", "D1", "--thread", "w1")
        self.land("lease", "renew", "L1", "--ttl-hours", "0", "--owner", "docs/@1")
        stale_brigade = "brigade: owner t1@1 is stale; this store is owned by t2@2"
        stale_land = "land: owner docs/@1 is stale; docs/ is at generation 2"
        land_script = str(ROOT / "t3/added/landing/scripts/land.py")
        commands = [
            ("pause", ["--store", str(self.store), "--at", str(docs), *old, "ticket", "add", "--summary", "late"], stale_brigade),
            ("pause", ["--store", str(self.store), "--at", str(docs), *old, "dish", "D1", "--state", "dropped", "--stopped", "r1"],
             stale_brigade),
            ("land-pause", ["--repo", str(self.project), "lease", "release", "L1", "--owner", "docs/@1"], stale_land),
            ("land-pause", ["--repo", str(self.project), "lease", "renew", "L1", "--owner", "docs/@1"], stale_land),
        ]
        running = []
        for number, (mode, args, message) in enumerate(commands):
            case = Path(self.temporary.name) / f"stale{number}"
            case.mkdir()
            running.append((case, self._spawn_race(mode, case, args), message))
        for case, _, _ in running:
            _wait_for_path(case / "paused", timeout=20)
        self.run_at(docs, "set", "--thread", "t2", "--replace")
        self.assertIn("owner t2@2", self.run_at(docs, "--owner", "t2@2", "status"))
        tables = ("rail.tsv", "log.tsv", "dishes.tsv", "restaurant.json")
        after_replace = {name: (docs / name).read_bytes() for name in tables}
        row = self.lease_row(1)
        for case, proc, message in running:
            (case / "proceed").touch()
            code, _, err = self._finish_race(proc)
            self.assertEqual((code, err), (1, message))
        self.assertEqual(self.run_at(docs, *old, "set", "--thread", "t2", "--workers", "9", ok=False), stale_brigade)
        self.assertEqual(self.run_at(docs, *old, "set", "--thread", "t1", ok=False), "brigade: thread t2 already recorded")
        self.assertEqual({name: (docs / name).read_bytes() for name in tables}, after_replace)
        self.assertEqual(self.lease_row(1), row)
        new = ("--owner", "t2@2")
        self.assertEqual(self.run_at(docs, *new, "ticket", "add", "--summary", "late"), "T2")
        self.assertEqual(self.land("lease", "renew", "L1", "--owner", "docs/@2"), "L1 renewed")
        self.assertEqual(self.land("lease", "release", "L1", "--owner", "docs/@2"), "L1 released")
        self.assertEqual(self.run_at(docs, *new, "dish", "D1", "--state", "dropped", "--stopped", "r1"), "D1 dropped; T1 waiting again")
        self.assertEqual(self.land("owner", "--prefix", "docs/", "--generation", "2"), "docs/ at generation 2")
        self.assertEqual(self.land("owner", "--prefix", "docs/", "--generation", "1", ok=False),
                         "land: docs/ is at generation 2; a floor never lowers")

    def test_a_store_without_a_generation_works_until_set_thread_records_one(self):
        self.open()
        meta = json.loads((self.at / "restaurant.json").read_text())
        meta["thread"] = "t1"
        (self.at / "restaurant.json").write_text(json.dumps(meta))
        self.assertEqual(self.brigade("ticket", "add", "--summary", "legacy"), "T1")
        self.brigade("set", "--thread", "t1")
        self.assertEqual(self.brigade("ticket", "add", "--summary", "unowned", ok=False, owner=False),
                         "brigade: this store is owned by t1@1; pass --owner <thread>@<generation> from status")
        self.assertEqual(self.brigade("--owner", "t1@1", "ticket", "add", "--summary", "owned"), "T2")


    def mode_rows(self):
        return [line.split("\t")[1:] for line in (self.at / "log.tsv").read_text().splitlines()[1:]
                if line.split("\t")[1] == "mode"]

    def test_open_mode_records_light_and_set_mode_clears_it(self):
        self.assertEqual(self.brigade("open", "--project-root", str(self.project), "--name", "Perf", "--mode", "light"),
                         f"opened {self.at}")
        self.assertEqual(json.loads((self.at / "restaurant.json").read_text())["mode"], "light")
        self.assertIn("## Budget\n\nAny cap on parallel workers, and whether a provider's usage limit switches this restaurant "
                      "to light mode.\n", (self.at / "menu.md").read_text())
        self.brigade("set", "--thread", "c1")
        self.assertEqual(self.brigade("status"),
                         "thread c1\nreporting: milestones, no landing contract\nmode light\nowner c1@1")
        self.assertIn("  Perf (reports milestones, mode light): nothing on record", self.brigade("walk"))
        self.assertEqual(self.brigade("open", "--project-root", str(self.project), "--name", "Perf", "--mode", "full"),
                         f"exists {self.at}\nthread c1 already recorded\nmode stays light; change it with set --mode")
        self.assertEqual(json.loads(self.brigade("set", "--mode", "full"))["mode"], "full")
        self.assertEqual(self.brigade("set", "--mode", "fast", ok=False), 'brigade: --mode takes full, light, or ""')
        self.assertNotIn("mode", json.loads(self.brigade("set", "--mode", "")))
        self.assertEqual(self.brigade("status"), "thread c1\nreporting: milestones, no landing contract\nowner c1@1")
        self.assertIn("  Perf (reports milestones): nothing on record", self.brigade("walk"))
        self.assertEqual(self.brigade("open", "--project-root", str(self.project), "--name", "Perf", "--mode", "full"),
                         f"exists {self.at}\nthread c1 already recorded\nmode stays unset; change it with set --mode")

    def test_item_mode_flags_refuse_light_and_a_missing_reason_with_exit_1(self):
        self.fired_bug_fix()
        self.brigade("ticket", "add", "--summary", "t")
        before = (self.at / "log.tsv").read_bytes()
        refusals = [
            (("dish", "D1", "--mode", "light", "--reason", "r"),
             "brigade: an item's mode only moves to full; change the coordinator with set --mode light"),
            (("fire", "--tickets", "T2", "--station", "bug-fix", "--summary", "t", "--mode", "light", "--reason", "r"),
             "brigade: an item's mode only moves to full; change the coordinator with set --mode light"),
            (("dish", "D1", "--mode", "full"), 'brigade: --mode full needs --reason "<one line>"'),
            (("dish", "D1", "--mode", "full", "--reason", " "), 'brigade: --mode full needs --reason "<one line>"'),
            (("dish", "D1", "--reason", "r"), "brigade: --reason goes with --mode full"),
            (("dish", "D1", "--mode", "fast", "--reason", "r"), "brigade: --mode takes full, got 'fast'"),
            (("dish", "D1", "--mode", "full", "--reason", "r", "--state", "dropped"),
             "brigade: --mode full needs open work; run --state dropped without it"),
            (("dish", "D1", "--mode", "full", "--reason", "r", "--state", "queued"),
             "brigade: --mode full needs open work; run --state queued without it"),
        ]
        for args, message in refusals:
            result = subprocess.run([sys.executable, str(SCRIPT), "--store", str(self.store), "--at", str(self.at), *args],
                                    capture_output=True, text=True)
            self.assertEqual((result.returncode, result.stderr.strip()), (1, message), args)
        self.assertEqual((self.at / "log.tsv").read_bytes(), before)
        self.assertEqual(self.brigade("ticket", "list", "--state", "waiting"), "T2 waiting [user] t")

    def test_dish_mode_full_twice_keeps_the_first_reason(self):
        self.fired_bug_fix()
        self.assertEqual(self.brigade("dish", "D1", "--mode", "full", "--reason", "contested: x"),
                         "D1 in-progress, mode full: contested: x")
        self.assertEqual(self.brigade("dish", "D1", "--mode", "full", "--reason", "y"),
                         "D1 in-progress, mode full: contested: x")
        self.assertEqual([row[:4] for row in self.mode_rows()], [["mode", "D1", "full", "contested: x"]])
        self.assertEqual(self.brigade("dish", "D1", "--state", "blocked", "--mode", "full", "--reason", "y"),
                         "D1 blocked, mode full: contested: x")
        self.record("abc", "pass")
        self.brigade("dish", "D1", "--state", "queued")
        self.assertEqual(self.brigade("dish", "D1", "--mode", "full", "--reason", "z", ok=False),
                         "brigade: D1 is queued; only open work moves to full mode")
        self.brigade("dish", "D1", "--state", "merged")
        self.assertEqual(self.brigade("dish", "D1", "--mode", "full", "--reason", "z", ok=False),
                         "brigade: D1 is merged; only open work moves to full mode")
        self.assertEqual(len(self.mode_rows()), 1)

    def test_dish_mode_full_with_a_stale_owner_appends_nothing(self):
        self.fired_bug_fix()
        self.brigade("set", "--thread", "c1")
        self.brigade("set", "--thread", "c2", "--replace")
        stale = "brigade: owner c1@1 is stale; this store is owned by c2@2"
        before = (self.at / "log.tsv").read_bytes()
        self.assertEqual(self.brigade("--owner", "c1@1", "dish", "D1", "--mode", "full", "--reason", "r", ok=False), stale)
        self.assertEqual((self.at / "log.tsv").read_bytes(), before)
        self.brigade("dish", "D1", "--mode", "full", "--reason", "r")
        after = (self.at / "log.tsv").read_bytes()
        self.assertEqual(self.brigade("--owner", "c1@1", "dish", "D1", "--mode", "full", "--reason", "r", ok=False), stale)
        self.assertEqual((self.at / "log.tsv").read_bytes(), after)
        self.record("abc", "pass")
        self.brigade("dish", "D1", "--state", "merged")
        self.assertEqual(self.brigade("--owner", "c1@1", "dish", "D1", "--mode", "full", "--reason", "r", ok=False), stale)

    def test_fire_mode_full_records_the_escalation_after_the_dish_row(self):
        self.open()
        self.brigade("ticket", "add", "--summary", "lock order")
        self.assertEqual(self.brigade("fire", "--tickets", "T1", "--station", "bug-fix", "--summary", "Fix the lock order",
                                      "--mode", "full", "--reason", "tickets name a lock"), "D1")
        rows = [line.split("\t")[1:4] for line in (self.at / "log.tsv").read_text().splitlines()[1:]]
        self.assertEqual(rows[-3:], [["dish", "D1", "in-progress"], ["mode", "D1", "full"], ["ticket", "T1", "assigned"]])
        self.assertEqual(self.mode_rows()[0][3], "tickets name a lock")

    def test_a_refused_fire_mode_full_keeps_the_reason_in_the_unblocked_command(self):
        self.open()
        self.brigade("set", "--workers", "1")
        self.brigade("ticket", "add", "--summary", "one")
        self.brigade("ticket", "add", "--summary", "two")
        self.brigade("fire", "--tickets", "T1", "--station", "bug-fix", "--summary", "a")
        self.assertIn("nothing fired: 1 of 1 workers running",
                      self.brigade("fire", "--tickets", "T2", "--station", "bug-fix", "--summary", "Fix the lock order",
                                   "--mode", "full", "--reason", "tickets name a lock", ok=False))
        self.brigade("dish", "D1", "--state", "blocked")
        line = next(line for line in self.brigade("watch").splitlines() if line.startswith("T2:"))
        self.assertEqual(line, "T2: unblocked; run fire --tickets=T2 --station=bug-fix '--summary=Fix the lock order' "
                               "--timebox=60 --mode=full '--reason=tickets name a lock'")
        result = self.bash_unblocked(self.at, line)
        self.assertEqual((result.returncode, result.stdout.strip()), (0, "D2"), result.stderr)
        self.assertEqual([row[:4] for row in self.mode_rows()], [["mode", "D2", "full", "tickets name a lock"]])

    def test_close_lists_an_escalation_with_its_tickets(self):
        self.fired_bug_fix()
        self.brigade("close")
        self.brigade("dish", "D1", "--mode", "full", "--reason", "contested: two owners")
        text = self.brigade("close", "--dry-run")
        self.assertEqual(text.split("\n\n", 2)[2], "## Moved to full mode\n\n- D1 (T1): contested: two owners")


    SEAT_RULE = ("Seat rule. Copy the Mode value above into --brief-mode on every roles.py mode and roles.py show call you "
                 "make, and pass no other mode flag. Never pass --session-mode. Mode source names where your launcher's "
                 "decision came from. It does not make this thread a session.")
    WAIT = ("- Never end your turn while a child task you started with delegate_task is still open, per step 5 of the "
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
            "waiting_for_children, whatever hasPendingChildRuns says. Cancel a child task with task_cancel when it runs "
            "past its budget or stalls, per the runtime's Failure handling. A thread you launched with t3_thread_launch "
            "has no parent, so its finished turn never wakes you. While it stays healthy, repeat t3_thread_wait on its "
            "threadId with timeoutMs 300000 and read its activity with t3_thread_read. A timeout alone never stops it. "
            "Stop it with t3_thread_interrupt and then a terminal t3_thread_wait only when it stalls, with no new activity "
            "item for ten minutes per step 5 of the runtime's Delegation section, or runs past its budget. "
            "A long-lived owner your playbook supervises, such as an Orchestrate PR owner, follows the runtime's Top-level "
            "threads section and its playbook instead, and does not hold your report. Write the report only once every "
            "child task and every other thread you launched is terminal.")
    CONTESTED = ("- If you find the design contested, do not run interrogate. Stop at a verifiable point, commit, and write "
                 "Contested: <one-line reason> under the status line. The coordinator moves the work to full mode and gives "
                 "your report to a fresh worker.")
    REPEAT = ("- Under the status line, repeat this brief's Mode: line, and its Waived by mode: line when it has one. "
              "A step that line names is not a deviation.")
    BRIEF = ("brief", "D1", "--goal", "g", "--acceptance", "a", "--verify", "v", "--paths", "src/a.py", "--lease", "L1",
             "--base", "origin/main")

    def coordinator(self, station="feature", mode="light", *fire):
        self.open()
        (self.at / "menu.md").write_text("## Purpose\n\nFast.\n")
        self.brigade("set", "--thread", "c1")
        if mode:
            self.brigade("set", "--mode", mode)
        self.brigade("ticket", "add", "--summary", "one")
        self.brigade("fire", "--tickets", "T1", "--station", station, "--summary", "s", "--branch", "perf/d1",
                     "--thread", "w1", *fire)

    def head(self, *lines, station="feature"):
        return "\n".join([f"Use the poteto-mode skill and its `{station}` playbook.", *lines, "Gate: brigade", self.SEAT_RULE])

    def test_the_brief_pastes_the_runtime_seat_rule_unchanged(self):
        runtime = (ROOT / "t3/runtime.md").read_text()
        self.assertIn(f"  ```text\n  {self.SEAT_RULE}\n  ```", runtime)

    def test_the_runtime_still_states_the_bounded_wait(self):
        runtime = (ROOT / "t3/runtime.md").read_text()
        self.assertIn("does not end its turn while a child is open", runtime)
        self.assertIn("Decide completion by `workState` alone", runtime)
        self.assertIn("Its finished turn does not wake the launcher.", runtime)
        self.assertIn("interrupt with `t3_thread_interrupt`", runtime)

    def test_wait_rule_waits_out_an_ended_run(self):
        rule = runpy.run_path(str(SCRIPT))["WAIT_RULE"]
        for phrase in (
            "returns at once while workState is still working or waiting_for_children",
            "t3_thread_wait and timeoutMs 120000 on your own thread",
            "with runId set to its activeRunId from t3_thread_read",
            "never a shell sleep",
            "whose run is still open and whose last message holds the result is stalled after two minutes with no new activity, per step 5",
            "count ten minutes from its last activity item",
        ):
            self.assertIn(phrase, rule)
        self.assertEqual(rule, self.WAIT)

    def test_the_report_section_opens_with_the_bounded_wait(self):
        self.coordinator()
        text = self.brigade(*self.BRIEF)
        lines = text.splitlines()
        start = lines.index("REPORT:")
        write = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("- Write it to "))
        self.assertEqual(lines[start:write + 1], ["REPORT:", self.WAIT, lines[write]])

    def test_an_orchestrate_brief_carries_the_same_bounded_wait(self):
        self.coordinator(station="orchestrate", mode="full")
        text = self.brigade(*self.BRIEF)
        self.assertTrue(text.startswith("Use the poteto-mode skill and its `orchestrate` playbook.\n"), text[:80])
        self.assertEqual(text.split("REPORT:\n", 1)[1].splitlines()[0], self.WAIT)

    def test_a_first_light_feature_brief_prints_the_first_waivers(self):
        self.coordinator()
        text = self.brigade(*self.BRIEF)
        self.assertEqual(text.split("\n\n", 1)[0], self.head(
            "Playbook: playbooks/feature.md", "Mode: light", "Mode source: restaurant.json", "Attempt: first",
            "Waived by mode: Arena, Interrogate, Comment Sicko"))
        report = text.split("REPORT:\n", 1)[1].splitlines()
        self.assertEqual(report[2:4], [self.REPEAT, self.CONTESTED])
        self.assertTrue(report[4].startswith("- After that file is written, call t3_thread_send"), report[4])
        self.assertEqual((self.at / "briefs/D1.md").read_text().strip(), text)
        self.assertEqual(self.mode_rows(), [])

    def test_a_brief_without_a_mode_prints_the_default(self):
        self.coordinator(mode=None)
        text = self.brigade(*self.BRIEF)
        self.assertEqual(text.split("\n\n", 1)[0], self.head(
            "Playbook: playbooks/feature.md", "Mode: full", "Mode source: default", "Attempt: first"))
        self.assertIn(self.REPEAT, text)
        self.assertNotIn("Contested:", text)

    def test_one_send_back_briefs_a_fix_attempt(self):
        self.coordinator()
        self.record("a1", "send-back")
        text = self.brigade(*self.BRIEF)
        self.assertEqual(text.split("\n\n", 1)[0], self.head(
            "Playbook: playbooks/feature.md", "Mode: light", "Mode source: restaurant.json", "Attempt: fix",
            "Waived by mode: How, Architect, Arena, Interrogate, Comment Sicko"))

    def test_a_replaced_worker_keeps_the_attempt_and_adds_no_send_back(self):
        self.coordinator()
        self.brigade("dish", "D1", "--thread", "w2")
        self.brigade("dish", "D1", "--thread", "w3")
        self.assertIn("Mode: light\nMode source: restaurant.json\nAttempt: first\n", self.brigade(*self.BRIEF))
        self.record("a1", "send-back")
        self.brigade("dish", "D1", "--state", "in-progress")
        self.brigade("dish", "D1", "--thread", "w4")
        self.brigade("dish", "D1", "--thread", "w5")
        self.assertIn("Mode: light\nMode source: restaurant.json\nAttempt: fix\n", self.brigade(*self.BRIEF))
        self.assertEqual(self.mode_rows(), [])

    def test_member_send_backs_do_not_move_the_item_to_full(self):
        self.coordinator()
        self.record("a1", "send-back")
        self.brigade("dish", "D1", "--state", "in-progress")
        self.record("a2", "send-back", "--member", verifier="grok/grok-4.7")
        self.record("a2", "send-back", "--member", verifier="opencode/kimi-k3")
        self.assertIn("Mode: light\nMode source: restaurant.json\nAttempt: fix\n", self.brigade(*self.BRIEF))
        self.assertEqual(self.mode_rows(), [])

    def test_a_late_send_back_counts_and_leaves_the_fix_attempt_running(self):
        self.coordinator()
        self.record("a2", "send-back")
        self.brigade("dish", "D1", "--state", "in-progress")
        self.assertEqual(self.brigade("pass", "record", "D1", "--pr", "u/1", "--sha", "a1", "--verdict", "send-back",
                                      "--author", CLAUDE, "--verifier", CODEX, "--note", "round 1", "--late"),
                         "D1: late send-back on record; D1 stays in-progress")
        self.assertEqual(self.dish_fields("state", "pr", "sha", "thread"), ("in-progress", "", "a2", ""))
        self.assertEqual(self.brigade("pass", "check", "D1", "--sha", "a1", ok=False),
                         "brigade: D1 at a1: send-back (round 1)")
        self.assertEqual(self.pass_rows()[1][3:], ["a1", "send-back", CLAUDE, CODEX, "round 1", "", ""])
        self.assertIn("Mode: full\nMode source: escalated: second send-back\nAttempt: fix\n", self.brigade(*self.BRIEF))

    def test_a_fix_brief_names_the_report_of_the_latest_send_back(self):
        self.coordinator()
        first, second, panel = (self.review_file(f"D1-review-{name}.md") for name in ("1", "2", "2-panel-2"))
        line = "- A reviewer sent an earlier attempt back. Its findings: "
        self.record("a1", "send-back", "--report", first.name)
        self.assertIn(f"{line}{first}\n", self.brigade(*self.BRIEF))
        self.brigade("dish", "D1", "--state", "in-progress")
        self.record("a2", "send-back", "--report", second.name)
        self.record("a2", "send-back", "--member", "--report", panel.name, verifier="grok/grok-4.7")
        self.assertIn(f"{line}{second}\n", self.brigade(*self.BRIEF))
        self.brigade("dish", "D1", "--state", "in-progress")
        self.record("a3", "send-back")
        self.brigade("86", "add", "--dish", "D1", "--round-budget")
        self.brigade("86", "answer", "Q1", "--answer", "known limits")
        self.assertNotIn(line, self.brigade(*self.BRIEF))
        plain = self.review_file("D1-review.md")
        self.assertIn(f"{line}{plain}\n", self.brigade(*self.BRIEF))

    def test_a_queue_bounce_briefs_a_bounce_attempt(self):
        self.coordinator(station="bug-fix")
        self.record("a1", "pass")
        self.brigade("dish", "D1", "--state", "queued")
        self.brigade("dish", "D1", "--state", "in-progress")
        self.assertEqual(self.brigade(*self.BRIEF).split("\n\n", 1)[0], self.head(
            "Playbook: playbooks/bug-fix.md", "Mode: light", "Mode source: restaurant.json", "Attempt: bounce",
            "Waived by mode: How, Why, Architect, Comment Sicko", station="bug-fix"))

    def test_the_second_send_back_moves_the_item_to_full_once(self):
        self.coordinator()
        self.record("a1", "send-back")
        self.brigade("dish", "D1", "--state", "in-progress")
        self.record("a2", "send-back")
        escalated = self.head("Playbook: playbooks/feature.md", "Mode: full", "Mode source: escalated: second send-back",
                              "Attempt: fix")
        text = self.brigade(*self.BRIEF)
        self.assertEqual(text.split("\n\n", 1)[0], escalated)
        self.assertNotIn("Contested:", text)
        self.assertEqual([row[:4] for row in self.mode_rows()], [["mode", "D1", "full", "second send-back"]])
        self.brigade(*self.BRIEF)
        self.assertEqual(len(self.mode_rows()), 1)
        self.brigade("set", "--mode", "light")
        self.assertEqual(self.brigade(*self.BRIEF).split("\n\n", 1)[0], escalated)
        self.assertEqual(self.brigade("close", "--dry-run").split("## Moved to full mode\n\n", 1)[1].split("\n")[0],
                         "- D1 (T1): second send-back")

    def test_the_escalation_lives_in_the_log_and_a_stale_write_changes_no_row(self):
        self.coordinator()
        self.record("a1", "send-back")
        self.brigade("dish", "D1", "--state", "in-progress")
        self.record("a2", "send-back")
        self.brigade(*self.BRIEF)
        (self.at / "pass.tsv").write_text("\t".join(("at", "dish", "pr", "sha", "verdict", "author", "verifier", "note")) + "\n")
        self.brigade("set", "--mode", "light")
        self.assertIn("Mode: full\nMode source: escalated: second send-back\n", self.brigade(*self.BRIEF))
        self.brigade("set", "--thread", "c2", "--replace")
        before = (self.at / "log.tsv").read_bytes()
        self.assertEqual(self.brigade("--owner", "c1@1", "dish", "D1", "--mode", "full", "--reason", "late", ok=False),
                         "brigade: owner c1@1 is stale; this store is owned by c2@2")
        self.assertEqual(self.brigade("--owner", "c1@1", *self.BRIEF, ok=False),
                         "brigade: owner c1@1 is stale; this store is owned by c2@2")
        self.assertEqual((self.at / "log.tsv").read_bytes(), before)

    def test_set_mode_leaves_a_written_brief_unchanged(self):
        self.coordinator(mode="full")
        self.brigade(*self.BRIEF)
        written = (self.at / "briefs/D1.md").read_bytes()
        self.brigade("set", "--mode", "light")
        self.assertEqual((self.at / "briefs/D1.md").read_bytes(), written)
        self.assertIn("Mode: light\n", self.brigade(*self.BRIEF))

    def test_fire_mode_full_carries_its_reason_into_every_brief(self):
        self.coordinator("bug-fix", "light", "--mode", "full", "--reason", "tickets name a lock")
        self.assertIn("Mode: full\nMode source: escalated: tickets name a lock\nAttempt: first\nGate: brigade\n",
                      self.brigade(*self.BRIEF))
        self.assertEqual(len(self.mode_rows()), 1)

    def test_a_lease_over_a_configured_path_escalates_once(self):
        self.git_project()
        (self.project / ".pstack").mkdir()
        (self.project / ".pstack/t3-roles.json").write_text(json.dumps({"escalate": ["src/lock.py"]}))
        self.coordinator()
        brief = [*self.BRIEF]
        brief[brief.index("src/a.py")] = "src/lock.py"
        self.assertIn("Mode: full\nMode source: escalated: lease covers src/lock.py\n", self.brigade(*brief))
        self.assertIn("Mode: full\nMode source: escalated: lease covers src/lock.py\n", self.brigade(*self.BRIEF))
        self.assertEqual([row[:4] for row in self.mode_rows()], [["mode", "D1", "full", "lease covers src/lock.py"]])

    def test_a_station_that_is_not_a_playbook_briefs_only_the_mode(self):
        self.coordinator(station="correct")
        text = self.brigade(*self.BRIEF)
        self.assertEqual(text.split("\n\n", 1)[0], self.head("Mode: light", "Mode source: restaurant.json", station="correct"))

    def test_roles_mode_refuses_to_run_under_a_store_lock(self):
        glob = runpy.run_path(str(SCRIPT))["run"].__globals__
        glob["HELD_LOCKS"].append(Path("/store/held"))
        with self.assertRaises(glob["BrigadeError"]) as caught:
            glob["roles_mode"](None)
        self.assertEqual(str(caught.exception),
                         "roles.py may run git; release /store/held's store lock before resolving the mode")

    def test_a_roles_failure_refuses_the_brief_and_writes_nothing(self):
        self.coordinator()
        config = Path(os.environ["XDG_CONFIG_HOME"]) / "pstack-t3" / "roles.json"
        config.parent.mkdir(parents=True)
        config.write_text("{")
        before = (self.at / "log.tsv").read_bytes()
        error = self.brigade(*self.BRIEF, ok=False)
        self.assertTrue(error.startswith(f"brigade: roles.py mode refused the brief: {config}: invalid JSON"), error)
        self.assertFalse((self.at / "briefs/D1.md").exists())
        self.assertEqual((self.at / "log.tsv").read_bytes(), before)

    def paused_brief(self, case):
        case.mkdir()
        return self._spawn_race("brief-pause", case, ["--store", str(self.store), "--at", str(self.at),
                                                      *_owner_words(self.at), *self.BRIEF])

    def test_two_briefs_racing_append_one_mode_row(self):
        self.coordinator()
        self.record("a1", "send-back")
        self.brigade("dish", "D1", "--state", "in-progress")
        self.record("a2", "send-back")
        case = Path(self.temporary.name) / "race"
        first = self.paused_brief(case)
        _wait_for_path(case / "paused", timeout=20)
        second = self.brigade(*self.BRIEF)
        (case / "proceed").touch()
        code, out, err = self._finish_race(first)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out, second)
        self.assertEqual(len(self.mode_rows()), 1)

    def test_a_mode_set_while_roles_runs_is_in_the_brief(self):
        self.coordinator()
        case = Path(self.temporary.name) / "race"
        first = self.paused_brief(case)
        _wait_for_path(case / "paused", timeout=20)
        self.brigade("set", "--mode", "full")
        (case / "proceed").touch()
        code, out, err = self._finish_race(first)
        self.assertEqual((code, err), (0, ""))
        self.assertIn("Mode: full\nMode source: restaurant.json\n", out)

    def test_a_store_that_keeps_changing_refuses_the_brief_after_three_resolutions(self):
        self.coordinator()
        case = Path(self.temporary.name) / "race"
        case.mkdir()
        churning = self._spawn_race("brief-churn", case, ["--store", str(self.store), "--at", str(self.at),
                                                           *_owner_words(self.at), *self.BRIEF])
        self.assertEqual(self._finish_race(churning), (1, "", "brigade: D1 changed while resolving its mode; run brief again"))
        self.assertFalse((self.at / "briefs/D1.md").exists())


class StoresTest(unittest.TestCase):
    """Two or three coordinators on one project root, as `app/<name>` under the store."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.store = Path(self.temporary.name) / "store"
        self.project = (Path(self.temporary.name) / "app").resolve()
        self.project.mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def dir(self, name):
        return self.store / "app" / name

    def run_brigade(self, name, *args):
        if "--owner" not in args:
            args = (*_owner_words(self.dir(name)), *args)
        return subprocess.run([sys.executable, str(SCRIPT), "--store", str(self.store), "--at", str(self.dir(name)), *args],
                              capture_output=True, text=True)

    def brigade(self, name, *args, ok=True):
        result = self.run_brigade(name, *args)
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        return (result.stdout if ok else result.stderr).strip()

    def open(self, name, *extra):
        return self.brigade(name, "open", "--project-root", str(self.project), "--name", name, *extra)

    def child(self, mode, name, *args):
        return subprocess.run([sys.executable, str(Path(__file__).resolve()), "--race-child", mode, self.temporary.name,
                               "--store", str(self.store), "--at", str(self.dir(name)), *args],
                              capture_output=True, text=True, timeout=30, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))

    def paused(self, label, name, *args):
        """A command that has parsed its arguments and waits before it takes the store lock."""
        case = Path(self.temporary.name) / label
        case.mkdir()
        proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--race-child", "pause", str(case),
                                 "--store", str(self.store), "--at", str(self.dir(name)), *args],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        _wait_for_path(case / "paused", timeout=20)
        return case, proc

    def resume(self, case, proc):
        (case / "proceed").touch()
        _, err = proc.communicate(timeout=30)
        return proc.returncode, err.strip()

    def files(self, name):
        directory = self.dir(name)
        return {str(path.relative_to(directory)): path.read_bytes() for path in sorted(directory.rglob("*"))
                if path.is_file() and path.name != "restaurant.lock"}

    def rows(self, name, table):
        lines = (self.dir(name) / table).read_text().splitlines()
        return [line.split("\t") for line in lines[1:]]

    def inbox(self, name):
        return sorted(path.name for path in (self.dir(name) / "inbox").glob("*")) if (self.dir(name) / "inbox").exists() else []

    def handoff(self, source="core", target="engine", ref="https://github.com/o/r/issues/7"):
        """core owns github, files T1, and moves it to engine. Returns engine's inbox file."""
        self.open(source, "--intake", "github")
        self.open(target)
        self.brigade(source, "ticket", "add", "--summary", "Fix the cache", "--source", "github", "--ref", ref)
        self.brigade(source, "ticket", "move", "T1", "--to", target)
        return self.dir(target) / "inbox" / f"app~{source}~T1.json"


class HandoffTest(StoresTest):
    def test_ticket_add_takes_a_user_request_with_the_summary_of_a_moved_ticket(self):
        self.open("core")
        self.open("engine")
        self.brigade("core", "ticket", "add", "--summary", "Fix the cache")
        self.brigade("core", "ticket", "move", "T1", "--to", "engine")
        self.assertEqual(self.brigade("core", "ticket", "add", "--summary", "Fix the cache"), "T2")

    def test_from_report_files_the_same_report_name_in_two_siblings(self):
        body = "## Follow-ups\n\n- Shared text.\n"
        for name in ("core", "engine"):
            self.open(name)
            self.brigade(name, "ticket", "add", "--summary", "s")
            self.brigade(name, "fire", "--tickets", "T1", "--station", "bug-fix", "--summary", "Fix s")
            (self.dir(name) / "reports").mkdir(exist_ok=True)
            (self.dir(name) / "reports" / "D1.md").write_text(body)
            self.assertEqual(self.brigade(name, "ticket", "add", "--from-report", "reports/D1.md"),
                             f"T2 added from {name}/reports/D1.md#1: Shared text.")
        self.assertEqual(self.rows("engine", "rail.tsv")[1][2:], ["waiting", "report", "engine/reports/D1.md#1", "", "Shared text."])

    def test_a_sibling_cannot_claim_a_source_another_owns(self):
        self.open("docs", "--intake", "github")
        self.assertEqual(json.loads((self.dir("docs") / "restaurant.json").read_text())["intake"], ["github"])
        self.open("engine")
        self.assertEqual(self.brigade("engine", "set", "--intake", "github", ok=False),
                         "brigade: docs already owns intake from github; move tickets to it instead")
        self.assertEqual(self.brigade("engine", "open", "--project-root", str(self.project), "--name", "release",
                                      "--intake", "github", ok=False),
                         "brigade: docs already owns intake from github; move tickets to it instead")
        self.assertFalse(self.dir("release").exists())
        self.assertEqual(self.brigade("engine", "open", "--project-root", str(self.project), "--name", "engine",
                                      "--intake", "github"),
                         "\n".join([f"exists {self.dir('engine')}",
                                    "intake stays empty; change it with set --intake",
                                    f"sibling docs ({self.dir('docs')}), thread not recorded",
                                    "  purpose: not written yet",
                                    "  off the menu: not written yet"]))
        self.assertEqual(json.loads((self.dir("engine") / "restaurant.json").read_text())["intake"], [])

    def test_two_owners_of_one_source_both_refuse_to_file(self):
        self.open("core")
        self.open("docs")
        for name in ("core", "docs"):
            path = self.dir(name) / "restaurant.json"
            meta = json.loads(path.read_text())
            meta["intake"] = ["github"]
            path.write_text(json.dumps(meta))
        self.assertEqual(self.brigade("core", "ticket", "add", "--summary", "x", "--source", "github", ok=False),
                         "brigade: docs owns intake from github; ask it to file this and move it here")
        self.assertEqual(self.brigade("docs", "ticket", "add", "--summary", "x", "--source", "github", ok=False),
                         "brigade: core owns intake from github; ask it to file this and move it here")
        self.assertEqual(self.rows("core", "rail.tsv") + self.rows("docs", "rail.tsv"), [])
        self.assertEqual(self.brigade("core", "ticket", "add", "--summary", "from the user"), "T1")

    def test_one_ref_is_filed_once_while_live(self):
        ref = "https://github.com/o/r/issues/7"
        self.open("core", "--intake", "github")
        self.assertEqual(self.brigade("core", "ticket", "add", "--summary", "a", "--source", "github", "--ref", ref), "T1")
        self.assertEqual(self.brigade("core", "ticket", "add", "--summary", "b", "--source", "github", "--ref", f"  {ref} ", ok=False),
                         f"brigade: {ref} is already T1 (waiting); nothing added")
        self.brigade("core", "fire", "--tickets", "T1", "--station", "bug-fix", "--summary", "fix")
        self.assertEqual(self.brigade("core", "ticket", "add", "--summary", "b", "--ref", ref, ok=False),
                         f"brigade: {ref} is already T1 (assigned); nothing added")
        self.brigade("core", "ticket", "set", "T1", "--state", "done")
        self.assertEqual(self.brigade("core", "ticket", "add", "--summary", "reopened", "--source", "github", "--ref", ref), "T2")

    def test_dropping_a_source_with_a_waiting_ticket_is_refused(self):
        self.open("core", "--intake", "github,feed")
        self.brigade("core", "ticket", "add", "--summary", "a", "--source", "github")
        self.assertEqual(self.brigade("core", "set", "--intake", "feed", ok=False),
                         "brigade: T1 from github is waiting; finish, drop, or move it before dropping github from intake")
        self.brigade("core", "ticket", "set", "T1", "--state", "dropped")
        self.brigade("core", "set", "--intake", "feed")
        self.assertEqual(json.loads((self.dir("core") / "restaurant.json").read_text())["intake"], ["feed"])

    def test_move_hands_a_ticket_to_a_sibling_and_take_files_it(self):
        self.open("core", "--intake", "github")
        self.open("engine")
        self.brigade("engine", "set", "--thread", "thread-engine")
        self.brigade("core", "ticket", "add", "--summary", "Fix the cache", "--source", "github", "--ref", "R7")
        self.assertEqual(self.brigade("core", "ticket", "move", "T1", "--to", "engine"),
                         "T1 moved to engine; tell thread thread-engine")
        self.assertEqual(self.brigade("core", "ticket", "list"), "T1 moved [github] Fix the cache R7")
        self.assertEqual(self.brigade("core", "fire", "--tickets", "T1", "--station", "bug-fix", "--summary", "x", ok=False),
                         "brigade: T1 is moved, not waiting")
        self.assertEqual(self.brigade("core", "ticket", "set", "T1", "--state", "waiting", ok=False),
                         "brigade: T1 moved to engine; it is that coordinator's ticket now")
        self.assertEqual(json.loads((self.dir("engine") / "inbox" / "app~core~T1.json").read_text()),
                         {"handoff": "app/core/T1", "summary": "Fix the cache", "source": "github", "ref": "R7"})
        self.assertEqual(self.brigade("core", "watch"), "T1: moved to engine, waiting for ticket take")
        self.assertEqual(self.brigade("engine", "watch"), "handed to you: 1; run ticket take")
        self.assertEqual(self.brigade("engine", "status"),
                         "thread thread-engine\nreporting: milestones, no landing contract, handed to you: 1\nowner thread-engine@1")
        self.assertEqual(self.brigade("engine", "ticket", "take"), "T1 from app/core/T1: Fix the cache")
        self.assertEqual(self.brigade("engine", "ticket", "list"), "T1 waiting [github (from app/core/T1)] Fix the cache R7")
        self.assertEqual(self.inbox("engine"), [])
        self.assertEqual(self.brigade("core", "watch"), "no work in progress")
        self.assertEqual(self.brigade("engine", "watch"), "no work in progress")
        self.assertIn("## Handed to another coordinator\n\n- T1: Fix the cache (to engine)",
                      self.brigade("core", "close", "--dry-run"))
        self.assertEqual(self.brigade("engine", "ticket", "take"), "nothing handed to you")
        (self.dir("engine") / "inbox" / "app~core~T1.json").write_text("{}")
        self.assertEqual(self.brigade("core", "watch"), "no work in progress")

    def test_a_moved_ref_stays_live_through_each_move_until_the_end_of_the_chain_finishes(self):
        ref = "R7"
        self.open("core", "--intake", "github")
        self.open("docs")
        self.open("engine")
        self.brigade("core", "ticket", "add", "--summary", "s", "--source", "github", "--ref", ref)
        self.brigade("core", "ticket", "move", "T1", "--to", "docs")
        refused = f"brigade: {ref} is already T1 (moved); nothing added"
        self.assertEqual(self.brigade("core", "ticket", "add", "--summary", "s", "--source", "github", "--ref", ref, ok=False), refused)
        self.brigade("docs", "ticket", "take")
        self.brigade("docs", "ticket", "move", "T1", "--to", "engine")
        self.assertEqual(self.brigade("core", "ticket", "add", "--summary", "s", "--source", "github", "--ref", ref, ok=False), refused)
        self.brigade("engine", "ticket", "take")
        self.assertEqual(self.brigade("engine", "ticket", "list"), f"T1 waiting [github (from app/docs/T1)] s {ref}")
        self.assertEqual(self.brigade("core", "ticket", "add", "--summary", "s", "--source", "github", "--ref", ref, ok=False), refused)
        self.brigade("engine", "ticket", "set", "T1", "--state", "done")
        self.assertEqual(self.brigade("core", "ticket", "add", "--summary", "s", "--source", "github", "--ref", ref), "T2")

    def test_a_new_owner_refuses_a_ref_the_old_owner_still_holds_live(self):
        self.handoff(source="core", target="docs", ref="R7")
        self.open("engine")
        self.brigade("core", "set", "--intake", "")
        self.brigade("engine", "set", "--intake", "github")
        self.assertEqual(self.brigade("engine", "ticket", "add", "--summary", "s", "--source", "github", "--ref", "R7", ok=False),
                         "brigade: R7 is already T1 in core (moved); nothing added")
        self.assertEqual(self.brigade("engine", "ticket", "add", "--summary", "s", "--source", "github", "--ref", "R8"), "T1")

    def test_a_replaced_owners_paused_move_does_not_republish_the_handoff(self):
        self.open("core", "--intake", "github")
        self.open("engine")
        self.brigade("core", "set", "--thread", "t1")
        self.brigade("core", "ticket", "add", "--summary", "Fix the cache", "--source", "github", "--ref", "R7")
        self.brigade("core", "ticket", "move", "T1", "--to", "engine")
        # The handoff was never delivered, so a rerun of the move would publish it again.
        (self.dir("engine") / "inbox" / "app~core~T1.json").unlink()
        stale = self.paused("stale", "core", "--owner", "t1@1", "ticket", "move", "T1", "--to", "engine")
        missing = self.paused("missing", "core", "ticket", "move", "T1", "--to", "engine")
        self.brigade("core", "--owner", "t1@1", "set", "--thread", "t2", "--replace")
        before = {"core": self.files("core"), "engine": self.files("engine")}
        self.assertEqual(self.resume(*stale), (1, "brigade: owner t1@1 is stale; this store is owned by t2@2"))
        self.assertEqual(self.resume(*missing),
                         (1, "brigade: this store is owned by t2@2; pass --owner <thread>@<generation> from status"))
        self.assertEqual({"core": self.files("core"), "engine": self.files("engine")}, before)
        self.assertEqual(self.inbox("engine"), [])
        self.brigade("core", "--owner", "t2@2", "ticket", "move", "T1", "--to", "engine")
        self.assertEqual(self.inbox("engine"), ["app~core~T1.json"])

    def test_a_replaced_owners_paused_take_does_not_delete_the_inbox_file(self):
        inbox = self.handoff()
        self.brigade("engine", "set", "--thread", "e1")
        handed = inbox.read_bytes()
        self.assertEqual(self.brigade("engine", "--owner", "e1@1", "ticket", "take"), "T1 from app/core/T1: Fix the cache")
        # A take that filed the ticket and died before deleting the file leaves exactly this.
        inbox.write_bytes(handed)
        stale = self.paused("stale", "engine", "--owner", "e1@1", "ticket", "take")
        missing = self.paused("missing", "engine", "ticket", "take")
        self.brigade("engine", "--owner", "e1@1", "set", "--thread", "e2", "--replace")
        before = self.files("engine")
        self.assertEqual(self.resume(*stale), (1, "brigade: owner e1@1 is stale; this store is owned by e2@2"))
        self.assertEqual(self.resume(*missing),
                         (1, "brigade: this store is owned by e2@2; pass --owner <thread>@<generation> from status"))
        self.assertEqual(self.files("engine"), before)
        self.assertEqual(self.inbox("engine"), ["app~core~T1.json"])
        self.assertEqual(self.brigade("engine", "--owner", "e2@2", "ticket", "take"), "T1 from app/core/T1: Fix the cache")
        self.assertEqual(self.inbox("engine"), [])

    def test_a_move_interrupted_after_the_rewrite_publishes_once_on_rerun(self):
        self.open("core", "--intake", "github")
        self.open("engine")
        self.brigade("core", "ticket", "add", "--summary", "Fix the cache", "--source", "github", "--ref", "R7")
        died = self.child("die-before-publish", "core", "ticket", "move", "T1", "--to", "engine")
        self.assertEqual(died.returncode, 9, died.stderr)
        self.assertEqual(self.brigade("core", "ticket", "list"), "T1 moved [github] Fix the cache R7")
        self.assertEqual(self.inbox("engine"), [])
        self.assertEqual(self.brigade("core", "watch"),
                         "T1: moved to engine, not delivered; run ticket move T1 --to engine again")
        self.brigade("core", "ticket", "move", "T1", "--to", "engine")
        self.brigade("core", "ticket", "move", "T1", "--to", "engine")
        self.assertEqual(self.inbox("engine"), ["app~core~T1.json"])
        self.assertEqual([row[1:4] for row in self.rows("core", "log.tsv") if row[3] == "moved"], [["ticket", "T1", "moved"]])
        self.brigade("engine", "ticket", "take")
        self.brigade("core", "ticket", "move", "T1", "--to", "engine")
        self.assertEqual(self.inbox("engine"), [])

    def test_watch_says_undelivered_when_the_inbox_file_is_deleted_before_take(self):
        self.handoff().unlink()
        self.assertEqual(self.brigade("core", "watch"),
                         "T1: moved to engine, not delivered; run ticket move T1 --to engine again")

    def test_take_twice_with_the_file_copied_back_files_one_ticket(self):
        inbox = self.handoff()
        saved = inbox.read_bytes()
        self.brigade("engine", "ticket", "take")
        inbox.write_bytes(saved)
        self.assertEqual(self.brigade("engine", "ticket", "take"), "T1 from app/core/T1: Fix the cache")
        self.assertEqual(len(self.rows("engine", "rail.tsv")), 1)
        self.assertEqual([row for row in self.rows("engine", "log.tsv") if row[4] == "from app/core/T1"],
                         [[self.rows("engine", "log.tsv")[0][0], "ticket", "T1", "waiting", "from app/core/T1"]])
        self.assertEqual(self.inbox("engine"), [])

    def assert_one_handed_ticket(self, name="engine"):
        self.assertEqual([row[2:] for row in self.rows(name, "rail.tsv")],
                         [["waiting", "github (from app/core/T1)", "https://github.com/o/r/issues/7", "", "Fix the cache"]])
        log = (self.dir(name) / "log.tsv").read_text()
        self.assertTrue(log.endswith("\n"))
        self.assertTrue(all(len(line.split("\t")) == 5 for line in log.splitlines()))
        self.assertEqual([row[1:] for row in self.rows(name, "log.tsv") if "from app/core/T1" in row[4]],
                         [["ticket", "T1", "waiting", "from app/core/T1"]])
        self.assertEqual(self.inbox(name), [])
        self.assertEqual(sorted(path.name for path in self.dir(name).glob("*.tmp")), [])

    def test_a_take_killed_before_its_log_row_finishes_on_the_next_take(self):
        self.handoff()
        died = self.child("die-before-log", "engine", "ticket", "take")
        self.assertEqual(died.returncode, 9, died.stderr)
        self.assertEqual(len(self.rows("engine", "rail.tsv")), 1)
        self.assertEqual(self.rows("engine", "log.tsv"), [])
        self.brigade("engine", "ticket", "take")
        self.assert_one_handed_ticket()

    def test_a_take_killed_inside_the_log_append_recovers_the_tail(self):
        self.handoff()
        died = self.child("die-inside-log-append", "engine", "ticket", "take")
        self.assertEqual(died.returncode, 9, died.stderr)
        self.assertRegex((self.dir("engine") / "log.tsv").read_text(), r"\n[^\n]+\tticket\tT1\twaiting\tfro$")
        self.brigade("engine", "ticket", "take")
        self.assert_one_handed_ticket()

    def test_a_failure_inside_the_temp_file_write_leaves_the_same_end_state(self):
        self.handoff()
        module = runpy.run_path(str(SCRIPT))
        glob = module["run"].__globals__

        class FailingTempfile:
            @staticmethod
            def NamedTemporaryFile(*args, **kwargs):
                handle = tempfile.NamedTemporaryFile(*args, **kwargs)
                write = handle.write

                def fail(text):
                    write(text[:10])
                    handle.flush()
                    raise OSError(28, "No space left on device")

                handle.write = fail
                return handle

        glob["tempfile"] = FailingTempfile
        with self.assertRaises(OSError):
            glob["run"](["--at", str(self.dir("engine")), "ticket", "take"])
        glob["tempfile"] = tempfile
        self.assertEqual(self.rows("engine", "rail.tsv"), [])
        self.assertEqual(self.inbox("engine"), ["app~core~T1.json"])
        self.brigade("engine", "ticket", "take")
        self.assert_one_handed_ticket()

    def test_a_joined_line_stops_the_read_with_the_malformed_message(self):
        self.open("core")
        self.brigade("core", "ticket", "add", "--summary", "a")
        log = self.dir("core") / "log.tsv"
        stamp = "2026-10-06T00:00:00.000000+00:00"
        log.write_text(log.read_text() + f"{stamp}\tticket\tT6\twaiting\tfro{stamp}\tticket\tT7\twaiting\tnote\n")
        self.assertEqual(self.brigade("core", "ticket", "list", ok=False), "brigade: log.tsv line 3 is malformed; fix or remove it")
        log.write_text(log.read_text().replace(f"fro{stamp}\tticket\tT7\twaiting\tnote", "fro"))
        self.assertEqual(self.brigade("core", "ticket", "list"), "T1 waiting [user] a")
        log.write_text(log.read_text() + f"{stamp[:19]}\tticket")
        self.assertEqual(self.brigade("core", "ticket", "list"), "T1 waiting [user] a")
        log.write_text(log.read_text() + f"{stamp}\tticket\tT8\twaiting\tnote\n")
        self.assertEqual(self.brigade("core", "ticket", "list", ok=False), "brigade: log.tsv line 4 is malformed; fix or remove it")
        log.write_text(log.read_text().replace(f"{stamp[:19]}\tticket{stamp}", "2026-10-06"))
        self.assertEqual(self.brigade("core", "ticket", "list", ok=False), "brigade: log.tsv line 4 is malformed; fix or remove it")

    def test_a_table_that_is_not_utf8_names_the_line(self):
        self.open("core")
        self.brigade("core", "ticket", "add", "--summary", "a")
        rail = self.dir("core") / "rail.tsv"
        rail.write_bytes(rail.read_bytes() + b"\xff\n")
        self.assertEqual(self.brigade("core", "ticket", "list", ok=False),
                         "brigade: rail.tsv line 3 is malformed; fix or remove it")

    def test_a_short_append_restores_the_last_complete_row(self):
        from unittest import mock
        self.open("core")
        self.brigade("core", "ticket", "add", "--summary", "a")
        log = self.dir("core") / "log.tsv"
        complete = log.read_text()
        log.write_text(complete + "2026-10-06T00:00:00.000000+00:00\tticket\tT9\twai")
        glob = runpy.run_path(str(SCRIPT))["run"].__globals__
        restaurant = glob["Restaurant"](self.dir("core"))
        row = {"at": "2026-10-06T00:00:01.000000+00:00", "kind": "ticket", "id": "T2", "state": "waiting", "note": "b"}
        real_write = os.write
        with mock.patch.object(os, "write", lambda fd, data: real_write(fd, data[:7])):
            with self.assertRaises(glob["BrigadeError"]) as raised:
                restaurant.append("log.tsv", row)
        self.assertEqual(str(raised.exception), "wrote 7 of 53 bytes to log.tsv; nothing appended")
        self.assertEqual(log.read_text(), complete)
        restaurant.append("log.tsv", row)
        self.assertEqual(log.read_text(), complete + "2026-10-06T00:00:01.000000+00:00\tticket\tT2\twaiting\tb\n")

    def test_two_processes_appending_200_rows_each_leave_400_rows(self):
        self.open("core")
        procs = [subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--race-child", "append",
                                   self.temporary.name, str(self.dir("core")), label],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                  env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
                 for label in ("a", "b")]
        (Path(self.temporary.name) / "go").touch()
        for proc in procs:
            _, err = proc.communicate(timeout=60)
            self.assertEqual(proc.returncode, 0, err)
        rows = self.rows("core", "log.tsv")
        self.assertEqual(len(rows), 400)
        self.assertTrue(all(len(row) == 5 for row in rows))
        self.assertEqual(sorted(row[4] for row in rows),
                         sorted(f"{label} row {number}" for label in "ab" for number in range(200)))
        self.assertEqual(self.brigade("core", "ticket", "list"), "")


LAND_SCRIPT = ROOT / "t3/added/landing/scripts/land.py"


def _land_has_rulings():
    """Change 8's share, lease reserve, and contest commands, which the admin's rulings run."""
    for words in (("share",), ("lease", "reserve"), ("contest",)):
        result = subprocess.run([sys.executable, str(LAND_SCRIPT), *words, "--help"], capture_output=True, text=True)
        if result.returncode != 0:
            return False
    return True


class AdminTest(StoresTest):
    """The executive admin at `app/.admin`, beside the coordinators on the same root."""

    STAMP = "2026-10-06T00:00:00Z"

    def admin(self, *args, ok=True):
        return self.brigade(".admin", *args, ok=ok)

    def open_admin(self, *extra, ok=True):
        return self.brigade(".admin", "open", "--admin", "--project-root", str(self.project), *extra, ok=ok)

    def meta(self, name):
        return json.loads((self.dir(name) / "restaurant.json").read_text())

    def relays(self):
        """The admin's relay rows as (store@offset, the copied row)."""
        return [(row[2], json.loads(row[4])) for row in self.rows(".admin", "log.tsv") if row[1] == "relay"]

    def ruling_events(self):
        """Ruling log rows as (id, state, note)."""
        return [tuple(row[2:5]) for row in self.rows(".admin", "log.tsv") if row[1] == "ruling"]

    def cursor(self, name):
        return self.meta(".admin").get("cursors", {}).get(f"app/{name}", 0)

    def size(self, name, table="log.tsv"):
        return len((self.dir(name) / table).read_bytes())

    def admin_child(self, mode, label, *args):
        """A race child running brigade.py on the admin store, started and not yet finished."""
        case = Path(self.temporary.name) / label
        case.mkdir()
        proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--race-child", mode, str(case),
                                 "--store", str(self.store), "--at", str(self.dir(".admin")), *args],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        return case, proc

    def append_row(self, name, *fields):
        """Restaurant.append of one log.tsv row in its own process, started and not yet finished."""
        proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--race-child", "append-row", self.temporary.name,
                                 str(self.dir(name)), *fields],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        return proc

    def finish(self, proc):
        out, err = proc.communicate(timeout=30)
        return proc.returncode, out.strip(), err.strip()

    def with_thread(self, thread="t1"):
        """docs, engine, and the admin, with the admin's thread recorded at generation 1."""
        self.open("docs")
        self.open("engine")
        self.open_admin()
        self.admin("set", "--thread", thread)

    # The store.

    def test_two_admin_opens_at_once_leave_one_store(self):
        procs = [subprocess.Popen([sys.executable, str(SCRIPT), "--store", str(self.store), "open", "--admin",
                                   "--project-root", str(self.project)],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
        words = sorted(proc.communicate(timeout=30)[0].split()[0] for proc in procs)
        self.assertEqual(words, ["exists", "opened"])
        self.assertEqual(sorted(path.name for path in (self.store / "app").iterdir()), [".admin"])
        meta = self.meta(".admin")
        self.assertEqual((meta["role"], meta["projectRoot"]), ("admin", str(self.project)))
        self.assertTrue((self.dir(".admin") / "rulings.tsv").is_file())
        self.assertIn("## Priorities", (self.dir(".admin") / "menu.md").read_text())

    def test_open_admin_refuses_a_second_root_with_the_same_directory_name(self):
        other = Path(self.temporary.name) / "other" / "app"
        other.mkdir(parents=True)
        self.open_admin()
        before = (self.dir(".admin") / "restaurant.json").read_bytes()
        self.assertEqual(self.brigade(".admin", "open", "--admin", "--project-root", str(other), ok=False),
                         f"brigade: {self.dir('.admin')} already holds a coordinator for {self.project}; pick another --name")
        self.assertEqual((self.dir(".admin") / "restaurant.json").read_bytes(), before)
        self.assertEqual(self.open_admin("--name", "boss", ok=False), "brigade: open --admin takes no --name")
        self.assertEqual(self.brigade("docs", "open", "--project-root", str(self.project), ok=False),
                         "brigade: open needs --name, or --admin")

    def test_open_admin_prints_every_coordinator_and_walk_puts_it_first(self):
        self.open("docs")
        (self.dir("docs") / "menu.md").write_text("## Purpose\n\nKeep the docs right.\n\n## Off the menu\n\nEngine work\n")
        self.assertEqual(self.open_admin("--reporting", "digest"), "\n".join([
            f"opened {self.dir('.admin')}",
            f"sibling docs ({self.dir('docs')}), thread not recorded",
            "  purpose: Keep the docs right.",
            "  off the menu: Engine work",
        ]))
        self.open("engine")
        self.assertIn(f"sibling executive admin ({self.dir('.admin')}), thread not recorded",
                      self.brigade("engine", "open", "--project-root", str(self.project), "--name", "engine"))
        walked = self.brigade("docs", "walk", "--repo", str(self.project)).splitlines()
        self.assertEqual(walked[1:], [
            "  executive admin (reports digest): nothing on record",
            "    thread not recorded",
            "  docs (reports milestones): nothing on record",
            "    thread not recorded",
            "  engine (reports milestones): nothing on record",
            "    thread not recorded",
        ])

    def test_the_admin_store_refuses_work_commands(self):
        self.open_admin()
        refusal = "brigade: the executive admin routes work and never runs it"
        for args in (("fire", "--tickets", "T1", "--station", "feature", "--summary", "s"),
                     ("brief", "D1", "--goal", "g", "--verify", "v", "--base", "main", "--acceptance", "a"),
                     ("dish", "D1", "--state", "merged"),
                     ("dish", "D1", "--state", "dropped", "--stopped", "r1"),
                     ("pass", "check", "D1", "--sha", "abc"),
                     ("watch",)):
            self.assertEqual(self.admin(*args, ok=False), refusal, args)
        self.assertEqual(self.admin("ticket", "add", "--summary", "Add a FAQ"), "T1")
        self.assertEqual(self.admin("86", "add", "--question", "Which purpose?", "--options", "docs, engine",
                                    "--default", "docs"), "Q1")
        self.assertEqual(self.admin("status"),
                         "thread not recorded\nreporting: milestones, no landing contract, waiting tickets: 1, decisions for you: 1")

    def test_a_ref_moved_through_the_admin_frees_at_every_step_once_done(self):
        ref = "https://github.com/o/r/issues/7"
        self.open("core", "--intake", "github")
        for name in ("docs", "engine"):
            self.open(name)
        self.open_admin()

        def refused(ident):
            self.assertEqual(self.brigade("core", "ticket", "add", "--summary", "again", "--source", "github", "--ref", ref,
                                          ok=False), f"brigade: {ref} is already {ident} (moved); nothing added")

        self.assertEqual(self.brigade("core", "ticket", "add", "--summary", "Fix", "--source", "github", "--ref", ref), "T1")
        self.brigade("core", "ticket", "move", "T1", "--to", ".admin")
        refused("T1")
        self.assertEqual(self.admin("inbox", "take"), "T1 from app/core/T1: Fix")
        refused("T1")
        self.assertEqual(self.admin("ticket", "move", "T1", "--to", "docs"), "T1 moved to docs; no thread recorded for docs")
        refused("T1")
        self.assertEqual(self.brigade("docs", "inbox", "take"), "T1 from app/.admin/T1: Fix")
        refused("T1")
        self.brigade("docs", "ticket", "set", "T1", "--state", "done")
        self.assertEqual(self.brigade("core", "ticket", "add", "--summary", "Fix", "--source", "github", "--ref", ref), "T2")
        self.brigade("core", "ticket", "move", "T2", "--to", ".admin")
        self.assertEqual(self.admin("inbox", "take"), "T2 from app/core/T2: Fix")
        self.admin("ticket", "move", "T2", "--to", "docs")
        self.assertEqual(self.brigade("docs", "inbox", "take"), "T2 from app/.admin/T2: Fix")
        self.brigade("docs", "ticket", "move", "T2", "--to", ".admin")
        refused("T2")
        self.assertEqual(self.admin("inbox", "take"), "T3 from app/docs/T2: Fix")
        refused("T2")
        self.admin("ticket", "move", "T3", "--to", "engine")
        refused("T2")
        self.assertEqual(self.brigade("engine", "ticket", "take"), "T1 from app/.admin/T3: Fix")
        refused("T2")
        self.brigade("engine", "ticket", "set", "T1", "--state", "done")
        self.assertEqual(self.brigade("core", "ticket", "add", "--summary", "Fix", "--source", "github", "--ref", ref), "T3")

    def test_a_tracker_ref_the_admin_files_is_refused_again_and_reaches_the_coordinator_unchanged(self):
        ref = "app-7f3"
        self.open("engine")
        self.open_admin("--intake", "beads")

        def refused(store, ident, where=""):
            self.assertEqual(self.brigade(store, "ticket", "add", "--summary", "again", "--source", "user", "--ref", ref,
                                          ok=False), f"brigade: {ref} is already {ident}{where}; nothing added")

        self.assertEqual(self.admin("ticket", "add", "--summary", "Fix login", "--source", "beads", "--ref", ref), "T1")
        self.assertEqual(self.brigade("engine", "ticket", "add", "--summary", "Fix login", "--source", "beads", "--ref", ref,
                                      ok=False), "brigade: .admin owns intake from beads; ask it to file this and move it here")
        refused(".admin", "T1", " (waiting)")
        refused("engine", "T1", " in .admin (waiting)")
        self.assertEqual(self.admin("ticket", "move", "T1", "--to", "engine"), "T1 moved to engine; no thread recorded for engine")
        refused(".admin", "T1", " (moved)")
        self.assertEqual(self.brigade("engine", "inbox", "take"), "T1 from app/.admin/T1: Fix login")
        self.assertEqual(self.brigade("engine", "ticket", "list"), "T1 waiting [beads (from app/.admin/T1)] Fix login app-7f3")
        refused("engine", "T1", " (waiting)")
        refused(".admin", "T1", " (moved)")

    def test_rule_overrule_leaves_two_rows_and_close_lists_both(self):
        self.open("docs")
        self.open_admin()
        self.assertEqual(self.brigade("docs", "rule", "list", ok=False), "brigade: rule works only in the executive admin's store")
        self.assertEqual(self.admin("rule", "add", "--kind", "contested-paths", "--parties", "docs,engine",
                                    "--question", "Who claims README.md next?", "--rule", "age",
                                    "--decision", "docs claims README.md next"), "R1")
        self.assertEqual(self.admin("rule", "overrule", "R1", "--decision", "engine goes first"), "R2")
        rows = self.rows(".admin", "rulings.tsv")
        self.assertEqual([(row[0], row[2], row[3], row[5], row[6], row[7], row[8]) for row in rows], [
            ("R1", "contested-paths", "docs, engine", "age", "docs claims README.md next", "", "overruled"),
            ("R2", "contested-paths", "docs, engine", "user", "engine goes first", "R1", "in-force"),
        ])
        self.assertEqual(self.admin("rule", "list"), "\n".join([
            "R1 overruled contested-paths (docs, engine): Who claims README.md next? Decided by age: docs claims README.md next.",
            "R2 in-force contested-paths (docs, engine): Who claims README.md next? Decided by user: engine goes first. Supersedes R1.",
        ]))
        self.assertEqual(self.admin("rule", "list", "--state", "in-force").splitlines()[0][:12], "R2 in-force ")
        report = self.admin("close")
        self.assertIn("\n".join([
            "## Rulings", "",
            "- R1 overruled contested-paths (docs, engine): Who claims README.md next? Decided by age: docs claims README.md next.",
            "- R2 in-force contested-paths (docs, engine): Who claims README.md next? Decided by user: engine goes first. Supersedes R1.",
        ]), report)
        self.assertNotIn("## Rulings", self.admin("close"))
        self.assertEqual(self.admin("rule", "add", "--kind", "ownership", "--parties", "docs,engine", "--question", "Who owns T4?",
                                    "--rule", "priority", "--decision", "docs", "--supersedes", "R2"), "R3")
        self.assertEqual(self.admin("rule", "set", "R1", "--state", "done", ok=False),
                         "brigade: R1 is overruled; only an in-force ruling ends")
        self.assertEqual(self.admin("rule", "set", "R3", "--state", "expired"), "R3 expired")
        self.assertEqual(self.admin("rule", "set", "R3", "--state", "expired"), "R3 expired")
        self.assertEqual([row[8] for row in self.rows(".admin", "rulings.tsv")], ["overruled", "superseded", "expired"])
        self.assertEqual(self.admin("rule", "list", "--state", "in-force"), "no rulings")
        self.assertIn("invalid choice: 'guess'", self.admin("rule", "add", "--kind", "ownership", "--parties", "docs",
                                                          "--question", "q", "--rule", "guess", "--decision", "d", ok=False))

    def _ruling_section(self, *lines):
        return "\n".join(["## Rulings", "", *lines])

    def test_a_ruling_killed_before_its_log_row_is_named_by_the_next_close(self):
        self.open_admin()
        died = self.child("die-before-log", ".admin", "rule", "add", "--kind", "ownership", "--parties", "docs",
                          "--question", "Who owns this?", "--rule", "priority", "--decision", "docs")
        self.assertEqual(died.returncode, 9, died.stderr)
        self.assertEqual(self.admin("rule", "list"),
                         "R1 in-force ownership (docs): Who owns this? Decided by priority: docs.")
        section = self._ruling_section(
            "- R1 in-force ownership (docs): Who owns this? Decided by priority: docs.")
        self.assertIn(section, self.admin("close", "--dry-run"))
        self.assertEqual(self.ruling_events(), [])
        self.assertIn(section, self.admin("close"))
        self.assertEqual(self.ruling_events(), [("R1", "in-force", "docs")])
        self.assertNotIn("## Rulings", self.admin("close"))

    def test_an_overrule_killed_before_its_log_rows_is_named_by_the_next_close(self):
        self.open_admin()
        self.admin("rule", "add", "--kind", "contested-paths", "--parties", "docs,engine",
                   "--question", "Who claims README.md next?", "--rule", "age",
                   "--decision", "docs claims README.md next")
        died = self.child("die-before-log", ".admin", "rule", "overrule", "R1", "--decision", "engine goes first")
        self.assertEqual(died.returncode, 9, died.stderr)
        self.assertEqual(self.admin("rule", "list"), "\n".join([
            "R1 overruled contested-paths (docs, engine): Who claims README.md next? Decided by age: docs claims README.md next.",
            "R2 in-force contested-paths (docs, engine): Who claims README.md next? Decided by user: engine goes first. Supersedes R1.",
        ]))
        section = self._ruling_section(
            "- R1 overruled contested-paths (docs, engine): Who claims README.md next? Decided by age: docs claims README.md next.",
            "- R2 in-force contested-paths (docs, engine): Who claims README.md next? Decided by user: engine goes first. Supersedes R1.",
        )
        self.assertIn(section, self.admin("close", "--dry-run"))
        self.assertEqual(self.ruling_events(), [("R1", "in-force", "docs claims README.md next")])
        self.assertIn(section, self.admin("close"))
        self.assertEqual(self.ruling_events(), [
            ("R1", "in-force", "docs claims README.md next"),
            ("R2", "in-force", "engine goes first"),
            ("R1", "overruled", "replaced by R2"),
        ])
        self.assertNotIn("## Rulings", self.admin("close"))

    def test_an_ended_ruling_killed_before_its_log_row_is_named_by_the_next_close(self):
        self.open_admin()
        self.admin("rule", "add", "--kind", "ownership", "--parties", "docs",
                   "--question", "Who owns this?", "--rule", "priority", "--decision", "docs")
        died = self.child("die-before-log", ".admin", "rule", "set", "R1", "--state", "done")
        self.assertEqual(died.returncode, 9, died.stderr)
        self.assertEqual(self.admin("rule", "list"),
                         "R1 done ownership (docs): Who owns this? Decided by priority: docs.")
        section = self._ruling_section(
            "- R1 done ownership (docs): Who owns this? Decided by priority: docs.")
        self.assertIn(section, self.admin("close", "--dry-run"))
        self.assertEqual(self.ruling_events(), [("R1", "in-force", "docs")])
        self.assertIn(section, self.admin("close"))
        self.assertEqual(self.ruling_events(), [
            ("R1", "in-force", "docs"),
            ("R1", "done", "docs (done)"),
        ])
        self.assertNotIn("## Rulings", self.admin("close"))

    def test_the_next_rule_add_logs_a_killed_ruling_once(self):
        self.open_admin()
        died = self.child("die-before-log", ".admin", "rule", "add", "--kind", "ownership", "--parties", "docs",
                          "--question", "Who owns this?", "--rule", "priority", "--decision", "docs")
        self.assertEqual(died.returncode, 9, died.stderr)
        self.assertEqual(self.admin("rule", "add", "--kind", "ownership", "--parties", "engine",
                                    "--question", "Who owns T4?", "--rule", "priority", "--decision", "engine"), "R2")
        self.assertEqual(self.ruling_events(), [
            ("R1", "in-force", "docs"),
            ("R2", "in-force", "engine"),
        ])

    # Requests.

    def test_a_request_waits_in_the_inbox_until_done(self):
        self.open("docs")
        self.open_admin()
        self.brigade("docs", "set", "--thread", "th-docs")
        self.assertEqual(self.brigade("docs", "request", "--to", "docs", "x", ok=False),
                         "brigade: request works only in the executive admin's store")
        self.assertEqual(self.admin("request", "--to", "engine", "x", ok=False),
                         f"brigade: engine is not a sibling coordinator on {self.project}")
        line = "from-user docs: add a FAQ"
        self.assertEqual(self.admin("request", "--to", "docs", line), "A1 for docs; tell thread th-docs")
        self.assertEqual(self.inbox("docs"), ["A1.line"])
        # A failed send leaves the file. The coordinator's next wake prints it again.
        for _ in range(2):
            self.assertEqual(self.brigade("docs", "inbox", "take"), f"A1: {line}")
        self.assertIn("requests from the user: 1", self.brigade("docs", "status"))
        self.assertEqual(self.brigade("docs", "inbox", "done", "A1"), "A1 done")
        self.assertEqual(self.brigade("docs", "inbox", "done", "A1"), "A1 done")
        self.assertEqual(self.brigade("docs", "inbox", "done", "A2", ok=False), "brigade: no request A2 in the inbox")
        self.assertEqual(self.inbox("docs"), [])
        self.assertEqual(self.brigade("docs", "inbox", "take"), "nothing handed to you")
        self.assertNotIn("requests from the user", self.brigade("docs", "status"))
        self.assertEqual([row[1:4] for row in self.rows("docs", "log.tsv") if row[1] == "inbox-done"], [["inbox-done", "A1", "done"]])
        self.assertEqual([row[1:] for row in self.rows(".admin", "log.tsv") if row[1] == "request"],
                         [["request", "A1", "sent", f"to docs: {line}"]])

    def test_a_request_killed_before_its_file_is_republished_once(self):
        self.open("docs")
        self.open_admin()
        died = self.child("die-before-publish", ".admin", "request", "--to", "docs", "from-user docs: add a FAQ")
        self.assertEqual(died.returncode, 9, died.stderr)
        self.assertEqual(self.inbox("docs"), [])
        self.assertEqual(self.admin("request", "--republish"), "A1 republished for docs")
        self.assertEqual(self.admin("request", "--republish"), "nothing to republish")
        self.assertEqual(self.inbox("docs"), ["A1.line"])
        self.brigade("docs", "inbox", "done", "A1")
        self.assertEqual(self.admin("request", "--republish"), "nothing to republish")
        self.assertEqual(self.inbox("docs"), [])
        self.admin("sync")
        self.assertEqual(self.admin("request", "--republish"), "nothing to republish")
        self.assertEqual(self.inbox("docs"), [])

    def test_republish_before_sync_skips_a_request_the_coordinator_finished(self):
        self.open("core")
        self.open_admin()
        self.brigade("core", "set", "--thread", "core-thread")
        self.admin("set", "--thread", "admin-thread")
        self.assertEqual(self.admin("request", "--to", "core", "reports-to core admin-thread"),
                         "A1 for core; tell thread core-thread")
        self.assertEqual(self.brigade("core", "inbox", "take"), "A1: reports-to core admin-thread")
        self.assertEqual(self.brigade("core", "inbox", "done", "A1"), "A1 done")
        self.assertEqual(self.admin("request", "--republish"), "nothing to republish")
        self.assertEqual(self.inbox("core"), [])
        self.assertNotIn("requests from the user", self.brigade("core", "status"))

    def test_a_request_finished_while_republish_runs_stays_finished(self):
        self.open("core")
        self.open_admin()
        self.brigade("core", "set", "--thread", "core-thread")
        self.admin("request", "--to", "core", "reports-to core admin-thread")
        case, proc = self.admin_child("pause-after-finished", "republish", "request", "--republish")
        _wait_for_path(case / "paused", timeout=20)
        self.assertEqual(self.brigade("core", "inbox", "done", "A1"), "A1 done")
        self.assertEqual(self.inbox("core"), [])
        (case / "proceed").touch()
        code, out, err = self.finish(proc)
        self.assertEqual(code, 0, err)
        self.assertNotIn("requests from the user", self.brigade("core", "status"))
        self.assertEqual(self.brigade("core", "inbox", "take"), "nothing handed to you")
        self.assertEqual(self.inbox("core"), [])
        self.assertEqual(self.admin("request", "--republish"), "nothing to republish")
        self.assertEqual(self.inbox("core"), [])

    def test_a_replayed_from_user_request_files_no_second_ticket(self):
        self.open("docs")
        self.assertEqual(self.brigade("docs", "ticket", "add", "--summary", "Add a FAQ", "--request", "A1"), "T1")
        refusal = "brigade: request A1 is already T1; nothing added"
        self.assertEqual(self.brigade("docs", "ticket", "add", "--summary", "Add a FAQ", "--request", "A1", ok=False), refusal)
        self.brigade("docs", "ticket", "set", "T1", "--state", "done")
        self.assertEqual(self.brigade("docs", "ticket", "add", "--summary", "Add a FAQ", "--request", "A1", ok=False), refusal)
        self.assertEqual(self.brigade("docs", "ticket", "list"), "T1 done [user (request A1)] Add a FAQ")
        self.assertEqual(self.brigade("docs", "ticket", "add", "--summary", "Other", "--request", "A2"), "T2")

    # Sync.

    def test_sync_relays_each_row_once_and_a_kill_before_the_cursor_copies_nothing_twice(self):
        self.open("docs")
        self.open_admin()
        start = self.size("docs")
        self.brigade("docs", "ticket", "add", "--summary", "one")
        sync = self.admin("sync")
        self.assertRegex(sync, r"^docs \S+ ticket T1 waiting: one$")
        self.assertEqual([(ident, row["kind"], row["id"], row["state"], row["note"]) for ident, row in self.relays()],
                         [(f"app/docs@{start}", "ticket", "T1", "waiting", "one")])
        self.assertEqual(self.cursor("docs"), self.size("docs"))
        self.assertEqual(self.admin("sync"), "nothing new")
        self.brigade("docs", "ticket", "add", "--summary", "two")
        before = self.cursor("docs")
        died = self.child("die-before-cursor", ".admin", "sync")
        self.assertEqual(died.returncode, 9, died.stderr)
        self.assertEqual(self.cursor("docs"), before)
        self.assertEqual(len(self.relays()), 2)
        self.assertEqual(self.admin("sync"), "nothing new")
        self.assertEqual([row["note"] for _, row in self.relays()], ["one", "two"])
        self.assertEqual(self.cursor("docs"), self.size("docs"))

    def test_a_row_appended_while_sync_runs_is_relayed_once_even_with_an_older_timestamp(self):
        self.open("docs")
        self.open_admin()
        self.brigade("docs", "ticket", "add", "--summary", "one")
        case, proc = self.admin_child("pause", "sync", "sync")
        _wait_for_path(case / "paused", timeout=20)
        older = "2020-01-01T00:00:00Z"
        appended = self.append_row("docs", older, "ticket", "T9", "waiting", "late")
        self.assertEqual(self.finish(appended)[0], 0)
        (case / "proceed").touch()
        code, out, err = self.finish(proc)
        self.assertEqual(code, 0, err)
        self.assertEqual([row["note"] for _, row in self.relays()], ["one"])
        self.assertRegex(self.admin("sync"), rf"^docs {older} ticket T9 waiting: late$")
        self.assertEqual(self.admin("sync"), "nothing new")
        self.assertEqual([row["note"] for _, row in self.relays()], ["one", "late"])

    def test_an_older_sync_finishing_late_never_moves_the_cursor_back(self):
        self.open("docs")
        self.open_admin()
        self.brigade("docs", "ticket", "add", "--summary", "one")
        case, outer = self.admin_child("pause", "outer", "sync")
        _wait_for_path(case / "paused", timeout=20)
        self.brigade("docs", "ticket", "add", "--summary", "two")
        self.admin("sync")
        consumed = self.size("docs")
        self.assertEqual(self.cursor("docs"), consumed)
        (case / "proceed").touch()
        code, out, err = self.finish(outer)
        self.assertEqual((code, out), (0, "nothing new"), err)
        self.assertEqual(self.cursor("docs"), consumed)
        self.assertEqual([row["note"] for _, row in self.relays()], ["one", "two"])

    def test_sync_leaves_an_unfinished_tail_and_relays_the_repaired_row_once(self):
        self.open("engine")
        self.open("core")
        self.open_admin()
        for number in range(1, 7):
            self.brigade("engine", "ticket", "add", "--summary", f"engine {number}")
        for number in range(1, 6):
            self.brigade("core", "ticket", "add", "--summary", f"core {number}")
        self.brigade("engine", "ticket", "move", "T6", "--to", "core")
        self.admin("sync")
        died = self.child("die-inside-log-append", "core", "ticket", "take")
        self.assertEqual(died.returncode, 9, died.stderr)
        tail = self.cursor("core")
        self.assertRegex((self.dir("core") / "log.tsv").read_bytes()[tail:].decode(), r"^[^\n]+\tticket\tT6\twaiting\tfro$")
        relayed = len(self.relays())
        self.assertEqual(self.admin("sync"), "nothing new")
        self.assertEqual((len(self.relays()), self.cursor("core")), (relayed, tail))
        self.brigade("core", "ticket", "take")
        self.admin("sync")
        new = self.relays()[relayed:]
        self.assertEqual([(ident, row["kind"], row["id"], row["state"], row["note"]) for ident, row in new],
                         [(f"app/core@{tail}", "ticket", "T6", "waiting", "from app/engine/T6")])

    def test_a_joined_line_stops_sync_at_that_line(self):
        self.open("docs")
        self.open_admin()
        self.admin("sync")
        log = self.dir("docs") / "log.tsv"
        good = f"{self.STAMP}\tticket\tT1\twaiting\tgood\n"
        joined = f"{self.STAMP}\tticket\tT6\twaiting\tfro{self.STAMP}\tticket\tT7\twaiting\tnote\n"
        at = self.size("docs") + len(good)
        log.write_text(log.read_text() + good + joined + f"{self.STAMP}\tticket\tT8\twaiting\tafter\n")
        self.assertEqual(self.admin("sync", ok=False), f"brigade: app/docs/log.tsv at byte {at} is malformed; nothing past it relayed")
        self.assertEqual(self.cursor("docs"), at)
        self.assertEqual([row["note"] for _, row in self.relays()], ["good"])
        self.assertEqual(self.admin("sync", ok=False), f"brigade: app/docs/log.tsv at byte {at} is malformed; nothing past it relayed")
        self.assertEqual([row["note"] for _, row in self.relays()], ["good"])

    def test_a_reader_racing_a_tail_repair_relays_only_the_repaired_row(self):
        self.open("core")
        self.open_admin()
        self.admin("sync")
        log = self.dir("core") / "log.tsv"
        tail = self.size("core")
        self.assertEqual(self.cursor("core"), tail)
        log.write_bytes(log.read_bytes() + f"{self.STAMP}\tticket\tT6\twaiting\tfro".encode())
        case, sync = self.admin_child("read16", "reader", "sync")
        _wait_for_path(case / "paused", timeout=20)
        append = self.append_row("core", "2026-10-06T00:00:01Z", "ticket", "T7", "waiting", "from app/engine/T7")
        time.sleep(1)
        self.assertIsNone(append.poll(), "the append waits for the reader's lock")
        (case / "proceed").touch()
        code, out, err = self.finish(sync)
        self.assertEqual((code, out), (0, "nothing new"), err)
        self.assertEqual(self.cursor("core"), tail)
        self.assertEqual(self.finish(append)[0], 0)
        self.assertEqual(self.relays(), [])
        self.admin("sync")
        self.assertEqual(self.relays(), [(f"app/core@{tail}", {"at": "2026-10-06T00:00:01Z", "kind": "ticket", "id": "T7",
                                                                 "state": "waiting", "note": "from app/engine/T7"})])
        self.assertEqual(log.read_bytes()[tail:], b"2026-10-06T00:00:01Z\tticket\tT7\twaiting\tfrom app/engine/T7\n")

    def test_snapshot_under_another_stores_lock_raises_and_returns_nothing(self):
        self.open("docs")
        self.open_admin()
        glob = runpy.run_path(str(SCRIPT))["run"].__globals__
        admin = glob["Restaurant"](self.dir(".admin"))
        docs = glob["Restaurant"](self.dir("docs"))
        log = docs.dir / "log.tsv"
        start = log.stat().st_size
        tail = b"2026-10-06T00:00:00Z\tticket\tT6\twaiting\tfro"
        log.write_bytes(log.read_bytes() + tail)
        fabricated = b"2026-10-06T00:00:00Z\tticket\tT6\twaiting\tfrom app/engine/T7\n"
        reads = [0]

        def chunk(fd):
            data = os.read(fd, 16)
            reads[0] += len(data)
            if reads[0] == 42 and data:
                proc = subprocess.run([sys.executable, "-B", "-c",
                                       "import runpy,sys; g=runpy.run_path(sys.argv[1]); r=g['Restaurant'](sys.argv[2]); "
                                       "r.append('log.tsv',{'at':'2026-10-06T00:00:01Z','kind':'ticket','id':'T7',"
                                       "'state':'waiting','note':'from app/engine/T7'})",
                                       str(SCRIPT), str(docs.dir)],
                                      capture_output=True, text=True, timeout=3)
                self.assertEqual(proc.returncode, 0, proc.stderr)
            return data

        original_read = glob["read_chunk"]
        glob["read_chunk"] = chunk
        copied = b""
        with admin.locked():
            try:
                copied = docs.snapshot("log.tsv", start)
            except glob["BrigadeError"] as error:
                self.assertEqual(str(error),
                                 f"cannot read {docs.dir} while holding {admin.dir.resolve()}'s lock; "
                                 "read other stores before taking a lock")
            else:
                self.fail(f"snapshot returned {copied!r}")
        self.assertEqual(copied, b"")
        self.assertNotEqual(log.read_bytes()[start:], fabricated)
        glob["read_chunk"] = original_read
        with docs.locked():
            self.assertEqual(docs.snapshot("log.tsv", start), tail)

    # Recovery.

    def test_two_recoveries_racing_leave_one_claim(self):
        self.with_thread()
        procs = [subprocess.Popen([sys.executable, str(SCRIPT), "--store", str(self.store), "--at", str(self.dir(".admin")),
                                   "set", "--thread", f"recovering:{name}", "--replace", "--expect", "t1"],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for name in ("a", "b")]
        results = [(proc.communicate(timeout=30), proc.returncode) for proc in procs]
        self.assertEqual(sorted(code for _, code in results), [0, 1])
        meta = self.meta(".admin")
        self.assertIn(meta["thread"], ("recovering:a", "recovering:b"))
        self.assertEqual((meta["generation"], meta["previousThread"]), (2, "t1"))
        loser = next(err for (_, err), code in results if code == 1)
        self.assertEqual(loser.strip(), f"brigade: thread is {meta['thread']}, not t1; nothing replaced")

    def test_recovery_needs_a_stopped_run_and_retirement_raises_the_generation(self):
        self.with_thread()
        self.admin("set", "--schedule", "intake=s-1")
        self.assertEqual(self.admin("set", "--thread", "t9", "--replace", ok=False),
                         "brigade: the executive admin's thread changes only with --replace --expect <old>")
        claim = json.loads(self.admin("set", "--thread", "recovering:t9", "--replace", "--expect", "t1"))
        self.assertEqual((claim["thread"], claim["generation"], claim["previousThread"], claim["schedules"]),
                         ("recovering:t9", 2, "t1", {"intake": "s-1"}))
        before = (self.dir(".admin") / "restaurant.json").read_bytes()
        self.assertEqual(self.admin("set", "--thread", "t2", "--replace", "--expect", "recovering:t9", ok=False),
                         "brigade: the old run has not been confirmed stopped; wait for it with t3_thread_wait, then pass --stopped <run id>")
        self.assertEqual((self.dir(".admin") / "restaurant.json").read_bytes(), before)
        self.admin("set", "--thread", "t2", "--replace", "--expect", "recovering:t9", "--stopped", "r1")
        self.assertEqual(self.admin("status").splitlines()[0], "thread t2")
        self.assertEqual(self.admin("status").splitlines()[-1], "owner t2@3")
        self.assertEqual(self.meta(".admin")["previousThread"], "t1")
        self.assertEqual([row[1:] for row in self.rows(".admin", "log.tsv") if row[1] == "thread"], [
            ["thread", "t1@1", "recorded", "first thread"],
            ["thread", "recovering:t9@2", "recorded", "replaced t1"],
            ["thread", "t2@3", "recorded", "replaced recovering:t9; stopped r1"],
        ])
        self.admin("set", "--thread", "", "--replace", "--expect", "t2")
        self.assertEqual([row[2:] for row in self.rows(".admin", "log.tsv") if row[1] == "thread" and row[2] == "@4"],
                         [["@4", "recorded", "replaced t2"]])
        self.assertEqual(self.admin("--owner", "t2@3", "status").splitlines()[0], "thread not recorded")
        self.assertEqual(self.admin("--owner", "t2@3", "ticket", "add", "--summary", "late", ok=False),
                         "brigade: owner t2@3 is stale; this store is owned by @4")
        self.admin("set", "--thread", "recovering:t5", "--replace", "--expect", "")
        self.admin("set", "--thread", "t6", "--replace", "--expect", "recovering:t5", "--stopped", "gone")
        meta = self.meta(".admin")
        self.assertEqual((meta["thread"], meta["generation"], meta["previousThread"]), ("t6", 6, "t2"))

    def test_a_replacement_killed_before_the_metadata_write_retries_with_one_row(self):
        self.with_thread()
        self.admin("set", "--thread", "recovering:t9", "--replace", "--expect", "t1")
        died = self.child("die-before-thread", ".admin", "set", "--thread", "t2", "--replace",
                          "--expect", "recovering:t9", "--stopped", "r1")
        self.assertEqual(died.returncode, 9, died.stderr)
        meta = self.meta(".admin")
        self.assertEqual((meta["thread"], meta["generation"]), ("recovering:t9", 2))
        self.assertEqual([row[1:] for row in self.rows(".admin", "log.tsv") if row[2] == "t2@3"], [
            ["thread", "t2@3", "recorded", "replaced recovering:t9; stopped r1"],
        ])
        self.admin("set", "--thread", "t2", "--replace", "--expect", "recovering:t9", "--stopped", "r1")
        meta = self.meta(".admin")
        self.assertEqual((meta["thread"], meta["generation"], meta["previousThread"]), ("t2", 3, "t1"))
        self.assertEqual([row[2] for row in self.rows(".admin", "log.tsv") if row[1] == "thread" and row[2] == "t2@3"],
                         ["t2@3"])

    def test_a_replacement_killed_inside_the_log_leaves_the_old_thread(self):
        self.with_thread()
        self.admin("set", "--thread", "recovering:t9", "--replace", "--expect", "t1")
        before = (self.dir(".admin") / "restaurant.json").read_bytes()
        died = self.child("die-before-log", ".admin", "set", "--thread", "t2", "--replace",
                          "--expect", "recovering:t9", "--stopped", "r1")
        self.assertEqual(died.returncode, 9, died.stderr)
        self.assertEqual((self.dir(".admin") / "restaurant.json").read_bytes(), before)
        self.assertNotIn("stopped r1", (self.dir(".admin") / "log.tsv").read_text())
        self.admin("set", "--thread", "t2", "--replace", "--expect", "recovering:t9", "--stopped", "r1")
        meta = self.meta(".admin")
        self.assertEqual((meta["thread"], meta["generation"], meta["previousThread"]), ("t2", 3, "t1"))
        self.assertEqual([row[2:] for row in self.rows(".admin", "log.tsv") if "stopped r1" in row[4]],
                         [["t2@3", "recorded", "replaced recovering:t9; stopped r1"]])

    def test_the_claim_raises_the_admin_floor_in_the_landing_store(self):
        env = dict(os.environ, XDG_STATE_HOME=str(Path(self.temporary.name) / "state"))
        git = lambda *command: subprocess.run(command, cwd=self.project, capture_output=True, text=True, check=True)
        git("git", "init", "-q", "-b", "main")
        (self.project / "a.txt").write_text("a\n")
        git("git", "add", "-A")
        git("git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
        land = lambda *args: subprocess.run([sys.executable, str(LAND_SCRIPT), "--repo", str(self.project), *args],
                                            capture_output=True, text=True, env=env)
        self.assertEqual(land("init", "--trunk", "lane", "--mode", "local", "--base", "main").returncode, 0)
        self.open_admin()
        for args in (("set", "--thread", "t1"), ("set", "--thread", "recovering:t9", "--replace", "--expect", "t1")):
            result = subprocess.run([sys.executable, str(SCRIPT), "--store", str(self.store), "--at", str(self.dir(".admin")), *args],
                                    capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(land("owner", "--prefix", ".admin/", "--generation", "1").stderr.strip(),
                         "land: .admin/ is at generation 2; a floor never lowers")

    def test_expect_works_only_in_the_admin_store(self):
        self.open("docs")
        self.brigade("docs", "set", "--thread", "t1")
        self.assertEqual(self.brigade("docs", "set", "--thread", "t2", "--replace", "--expect", "t1", ok=False),
                         "brigade: --expect works only in the executive admin's store")
        self.assertEqual(self.meta("docs")["thread"], "t1")

    def test_a_log_write_that_read_restaurant_json_before_a_replacement_keeps_the_new_thread(self):
        self.with_thread()
        glob = runpy.run_path(str(SCRIPT))["run"].__globals__
        restaurant = glob["Restaurant"](self.dir(".admin"), "t1@1")
        self.assertEqual(restaurant.meta["thread"], "t1")
        self.admin("set", "--thread", "recovering:t9", "--replace", "--expect", "t1")
        after_claim = self.files(".admin")
        with self.assertRaises(glob["BrigadeError"]) as raised:
            restaurant.log("ticket", "T1", "waiting", "one")
        self.assertEqual(str(raised.exception), "owner t1@1 is stale; this store is owned by recovering:t9@2")
        self.assertEqual(self.files(".admin"), after_claim)
        unfenced = glob["Restaurant"](self.dir(".admin"))
        unfenced.unfenced = True
        unfenced.log("ticket", "T1", "waiting", "one")
        meta = self.meta(".admin")
        self.assertEqual((meta["thread"], meta["generation"], meta["previousThread"]), ("recovering:t9", 2, "t1"))

    def test_reports_to_is_recorded_cleared_and_shown_by_status(self):
        self.open("docs")
        self.brigade("docs", "set", "--thread", "th-docs")
        self.brigade("docs", "set", "--reports-to", "th-admin")
        self.assertEqual(self.meta("docs")["reportsTo"], "th-admin")
        self.assertEqual(self.brigade("docs", "status"),
                         "thread th-docs\nreporting: milestones, no landing contract\nreports to th-admin\nowner th-docs@1")
        self.brigade("docs", "set", "--reports-to", "")
        self.assertNotIn("reportsTo", self.meta("docs"))
        self.assertEqual(self.brigade("docs", "status"), "thread th-docs\nreporting: milestones, no landing contract\nowner th-docs@1")

    # The owner fence.

    def test_claim_first_then_a_paused_rule_add_is_refused(self):
        self.with_thread()
        case, proc = self.admin_child("pause", "rule", "--owner", "t1@1", "rule", "add", "--kind", "ownership",
                                      "--parties", "docs,engine", "--question", "Who owns T1?", "--rule", "priority",
                                      "--decision", "docs")
        _wait_for_path(case / "paused", timeout=20)
        self.admin("set", "--thread", "recovering:t9", "--replace", "--expect", "t1")
        after_claim = self.files(".admin")
        (case / "proceed").touch()
        code, _, err = self.finish(proc)
        self.assertEqual((code, err), (1, "brigade: owner t1@1 is stale; this store is owned by recovering:t9@2"))
        self.assertEqual(self.files(".admin"), after_claim)
        self.assertEqual(self.rows(".admin", "rulings.tsv"), [])

    def test_after_a_terminal_wait_the_old_runs_paused_commands_change_nothing(self):
        self.with_thread()
        self.brigade("docs", "ticket", "add", "--summary", "one")
        self.admin("ticket", "add", "--summary", "route me")
        old = ("--owner", "t1@1")
        paused = [self.admin_child("pause", f"stale{number}", *old, *args) for number, args in enumerate((
            ("rule", "add", "--kind", "ownership", "--parties", "docs,engine", "--question", "q", "--rule", "priority", "--decision", "d"),
            ("request", "--to", "docs", "from-user docs: late"),
            ("sync",),
            ("ticket", "move", "T1", "--to", "docs"),
        ))]
        for case, _ in paused:
            _wait_for_path(case / "paused", timeout=20)
        self.admin("set", "--thread", "recovering:t9", "--replace", "--expect", "t1")
        self.admin("set", "--thread", "t2", "--replace", "--expect", "recovering:t9", "--stopped", "r1")
        self.assertEqual(self.admin("status").splitlines()[-1], "owner t2@3")
        self.assertIn("docs", self.admin("sync"))
        admin_after, docs_after = self.files(".admin"), self.files("docs")
        for case, proc in paused:
            (case / "proceed").touch()
            code, _, err = self.finish(proc)
            self.assertEqual((code, err), (1, "brigade: owner t1@1 is stale; this store is owned by t2@3"))
        self.assertEqual(self.files(".admin"), admin_after)
        self.assertEqual(self.files("docs"), docs_after)
        self.assertEqual(self.inbox("docs"), [])

    def test_a_write_that_took_the_lock_before_the_claim_finishes_first(self):
        self.with_thread()
        case, proc = self.admin_child("hold", "hold", "--owner", "t1@1", "rule", "add", "--kind", "ownership",
                                      "--parties", "docs,engine", "--question", "Who owns T1?", "--rule", "priority",
                                      "--decision", "docs")
        _wait_for_path(case / "holding", timeout=20)
        claim = subprocess.Popen([sys.executable, str(SCRIPT), "--store", str(self.store), "--at", str(self.dir(".admin")),
                                  "set", "--thread", "recovering:t9", "--replace", "--expect", "t1"],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(lambda: claim.poll() is None and claim.kill())
        time.sleep(0.5)
        self.assertIsNone(claim.poll(), "the claim waits for the lock")
        (case / "proceed").touch()
        self.assertEqual(self.finish(proc)[:2], (0, "R1"))
        self.assertEqual(self.finish(claim)[0], 0)
        kinds = [(row[1], row[2]) for row in self.rows(".admin", "log.tsv")]
        self.assertLess(kinds.index(("ruling", "R1")), kinds.index(("thread", "recovering:t9@2")))
        self.assertEqual(self.meta(".admin")["thread"], "recovering:t9")

    @unittest.skipUnless(_land_has_rulings(), "land.py has no share, lease reserve, or contest yet; change 8 adds them, "
                                              "and this test runs once it lands")
    def test_after_a_recovery_the_old_runs_paused_land_rulings_change_nothing(self):
        state = Path(self.temporary.name) / "state"
        env = dict(os.environ, XDG_STATE_HOME=str(state))
        from unittest import mock
        patcher = mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(state)})
        patcher.start()
        self.addCleanup(patcher.stop)

        def land(*args, ok=True):
            result = subprocess.run([sys.executable, str(LAND_SCRIPT), "--repo", str(self.project), *args],
                                    capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
            return (result.stdout if ok else result.stderr).strip()

        git = lambda *command: subprocess.run(command, cwd=self.project, capture_output=True, text=True, check=True)
        git("git", "init", "-q", "-b", "main")
        (self.project / "README.md").write_text("a\n")
        git("git", "add", "-A")
        git("git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
        land("init", "--trunk", "lane", "--mode", "local", "--base", "main", "--cap", "3")
        self.with_thread()
        contest = land("contest", "--holders", "docs/D1,engine/D1", "--owner", ".admin/@1")
        old = ("--owner", ".admin/@1")
        commands = [("share", "--for", "docs/", "1", *old),
                    ("lease", "reserve", "--for", "docs/", "--paths", "README.md", "--ruling", "R1", *old),
                    ("contest", "--settle", contest, "--first", "docs/D1", *old)]
        running = []
        for number, args in enumerate(commands):
            case = Path(self.temporary.name) / f"land{number}"
            case.mkdir()
            proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--race-child", "land-pause", str(case),
                                     "--repo", str(self.project), *args],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
            self.addCleanup(lambda proc=proc: proc.poll() is None and proc.kill())
            running.append((case, proc))
        for case, _ in running:
            _wait_for_path(case / "paused", timeout=20)
        self.admin("set", "--thread", "recovering:t9", "--replace", "--expect", "t1")
        self.admin("set", "--thread", "t2", "--replace", "--expect", "recovering:t9", "--stopped", "r1")
        before = (land("lease", "list"), land("status"))
        for case, proc in running:
            (case / "proceed").touch()
            code, _, err = self.finish(proc)
            self.assertEqual((code, err), (1, "land: owner .admin/@1 is stale; .admin/ is at generation 3"))
        self.assertEqual((land("lease", "list"), land("status")), before)


class SeatLaunchDocTest(unittest.TestCase):
    def setUp(self):
        self.skill = (ROOT / "skills/brigade/SKILL.md").read_text()
        service = self.skill.split("## Run a service", 1)[1].split("\n## ", 1)[0]
        self.launch = next(line for line in service.splitlines() if line.startswith("   3. Launch the worker"))
        self.review = next(line for line in service.splitlines() if line.startswith("6. **Review.**"))

    def test_step_4_3_links_both_runtime_anchors_and_records_after_the_match(self):
        self.assertIn("../pstack-runtime/SKILL.md#top-level-threads", self.launch)
        self.assertIn("../pstack-runtime/SKILL.md#delegation", self.launch)
        self.assertIn("Step 4.4 records the thread only after the readback matches.", self.launch)

    def test_step_6_reads_configuration_before_the_verdict(self):
        self.assertIn(
            "Right after the spawn, confirm its options with `t3_thread_configuration` on the returned `childThreadId` before the verdict counts",
            self.review,
        )


class LivenessIdleDocTest(unittest.TestCase):
    def test_step_5_nudges_an_idle_worker_with_its_timebox_open(self):
        text = (ROOT / "t3/added/brigade/SKILL.md").read_text()
        section = text.split("## Liveness check", 1)[1].split("\n## ", 1)[0]
        step = next(line for line in section.splitlines() if line.startswith("5. "))
        self.assertIn("activeRunId", step)
        self.assertIn("nudge-<dish>-<that run id>", step)
        self.assertIn("goes to step 4", step)

    def test_a_held_item_skips_liveness_steps_2_to_5(self):
        text = (ROOT / "t3/added/brigade/SKILL.md").read_text()
        section = text.split("## Liveness check", 1)[1].split("\n## ", 1)[0]
        self.assertIn(
            "`D1: open decision Q1: <question>; launch no worker or verifier until 86 answer Q1`",
            section,
        )
        self.assertIn("Launch nothing and spawn nothing.", section)
        self.assertIn("Skip Liveness steps 2 to 5 for that item.", section)
        self.assertIn("Step 4.4 records that thread", section)
        self.assertNotIn("Step 4.3 records that thread", section)
        self.assertNotIn("Skip this line while `$B 86 list` parks that dish.", section)


class UsageLimitDocTest(unittest.TestCase):
    def test_step_7_relaunches_a_usage_limit_before_the_light_mode_question(self):
        text = (ROOT / "t3/added/brigade/SKILL.md").read_text()
        service = text.split("## Run a service", 1)[1].split("\n## ", 1)[0]
        bullet = next(line for line in service.splitlines() if line.startswith("   - Usage limit:"))
        self.assertIn("../pstack-runtime/SKILL.md#failure-handling", bullet)
        self.assertIn("roles.py backup", bullet)
        self.assertIn("The dish keeps its lease", bullet)
        self.assertIn("Never call `t3_thread_send` on the old worker.", bullet)
        question = (
            '$B 86 add --question "<provider> hit its usage limit. '
            'Run new work in light mode until it resets?" '
            '--options "light, full" --default "light"'
        )
        self.assertIn(question, bullet)
        self.assertLess(bullet.index("t3_thread_interrupt"), bullet.index("roles.py backup"))
        self.assertLess(bullet.index("roles.py backup"), bullet.index(question))
        self.assertIn("../pstack-runtime/SKILL.md#modes", bullet)
        self.assertIn("../pstack-runtime/SKILL.md#gate-review", bullet)
        self.assertIn("each code delegate's `providerInstanceId/model`", bullet)
        self.assertIn("Never pass only the worker's model when a delegate wrote the code.", bullet)
        self.assertIn("--resume", bullet)
        self.assertIn("keeps its lease and its branch", bullet)
        self.assertIn("A new branch never widens the lease.", bullet)
        self.assertLess(bullet.index("On `park`"), bullet.index("--resume"))
        self.assertIn("A parked verifier stays in review.", bullet)
        self.assertNotIn("relaunch per this bullet on the first service after it", bullet)

    def test_step_7_runs_a_review_backups_panel(self):
        text = (ROOT / "t3/added/brigade/SKILL.md").read_text()
        service = text.split("## Run a service", 1)[1].split("\n## ", 1)[0]
        bullet = next(line for line in service.splitlines() if line.startswith("   - Usage limit:"))
        relaunch = "When it prints `relaunch`, spawn a fresh verifier per step 6 on the printed seat."
        panel = (
            "When it prints `panel`, spawn one fresh verifier per step 6 on each printed seat, "
            "keep the dish in review until every one is terminal, then apply the printed rule per "
            "[Failure handling](../pstack-runtime/SKILL.md#failure-handling)."
        )
        rows = (
            "Run `$B pass record` once for each member that returned a verdict, "
            "with that member's seat as `--verifier` and its file as `--report`."
        )
        passes = (
            "When the rule passes, record each passing member's `pass` with no other flag "
            "and every other member with `--member`."
        )
        resumed = "When `--resume` prints `panel`, run the panel the same way."
        for phrase in (
            panel,
            "`<restaurant dir>/reports/<dish>-review-<k>-panel-<n>.md`",
            rows,
            passes,
            "record that member's `send-back` with no other flag and every other member with `--member`",
            "When fewer than two pass and none reproduces a blocker, record every member with `--member`, "
            "and the dish stays in review as on `park`.",
            resumed,
        ):
            self.assertIn(phrase, bullet)
        self.assertNotIn("copy its findings", bullet)
        self.assertLess(bullet.index(relaunch), bullet.index(panel))
        self.assertLess(bullet.index(panel), bullet.index("On `park`"))
        self.assertLess(bullet.index("When `--resume` prints `relaunch` for `verifiers`"), bullet.index(resumed))


class RoundBudgetDocTest(unittest.TestCase):
    def setUp(self):
        self.text = (ROOT / "t3/added/brigade/SKILL.md").read_text()
        self.service = self.text.split("## Run a service", 1)[1].split("\n## ", 1)[0].splitlines()

    def test_the_script_section_names_the_closing_answers_and_the_budget(self):
        script = self.text.split("## The script", 1)[1].split("\n## ", 1)[0]
        self.assertIn("A dish's round count is its send-backs written after the later of its last passing verdict "
                      "and its last answered round decision.", script)
        self.assertIn("A dish owes a round decision while that count is three or more and its state is "
                      "`in-progress`, `in-review`, `sent-back`, or `blocked`.", script)
        self.assertIn("Only `known limits`, `redesign`, or `drop` closes it.", script)
        self.assertIn("No other decision's answer restarts the count.", script)
        self.assertIn("The budget refuses nothing else.", script)
        for command in ("`dish --state in-progress`", "`dish --thread` or `--task`", "a `brief` whose fields parse",
                        "`fire` exits 1 on a ticket of that dish"):
            self.assertIn(command, script)
        self.assertIn("`ROUND_BUDGET`", script)
        for old in ("whatever state", "after the dish is dropped", "A queue bounce of that dish is refused"):
            self.assertNotIn(old, script)

    def test_step_6_records_every_round_with_its_report(self):
        review = next(line for line in self.service if line.startswith("6. **Review.**"))
        self.assertTrue(review.endswith(
            "Record every round, pass or fail, with `$B pass record` at the reviewed SHA and `--report <that file>`."
        ))

    def test_step_7_stops_fix_rounds_at_a_pending_decision(self):
        pending = [line for line in self.service
                   if line.startswith("   - When `pass record` or `watch` prints `<n> send-backs, decision pending`,")]
        self.assertEqual(len(pending), 1)
        bullet = pending[0]
        send_back = next(line for line in self.service if line.startswith("   - `send-back`:"))
        self.assertLess(self.service.index(bullet), self.service.index(send_back))
        self.assertIn("`$B 86 add --dish <id> --round-budget`", bullet)
        self.assertIn('`$B 86 answer Q<n> --answer "<option>"`', bullet)
        self.assertIn("On `known limits`", bullet)
        self.assertIn("On `redesign`", bullet)
        self.assertIn("On `drop`", bullet)
        self.assertIn("Finish with the old worker", bullet)
        self.assertIn("launch no fix worker", bullet)
        self.assertIn("Follow this bullet in place of the `send-back` bullet below.", bullet)
        self.assertNotIn("bounce", bullet)
        self.assertNotIn("decision pending", send_back)

    def test_the_liveness_check_points_a_pending_decision_at_step_7(self):
        section = self.text.split("## Liveness check", 1)[1].split("\n## ", 1)[0]
        lines = [line for line in section.splitlines() if line.startswith("   - `D1: 3 send-backs, decision pending`.")]
        self.assertEqual(len(lines), 1)
        self.assertIn("decision-pending bullet in Run a service step 7", lines[0])


class AnswerRelayDocTest(unittest.TestCase):
    def test_the_requests_answer_row_names_still_open(self):
        text = (ROOT / "t3/added/brigade/SKILL.md").read_text()
        requests = text.split("**Requests.**", 1)[1].split("\n**", 1)[0]
        row = next(line for line in requests.splitlines() if line.startswith("| `answer "))
        self.assertIn("still open", row)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--race-child":
        try:
            _race_child(sys.argv[2], sys.argv[3], sys.argv[4:])
        except TimeoutError as error:
            print(f"race child timed out waiting for {error}", file=sys.stderr)
            sys.exit(2)
    else:
        unittest.main()
