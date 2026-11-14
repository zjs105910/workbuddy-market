import os
import pathlib
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import release  # noqa: E402
import test_pstack_t3  # noqa: E402

ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "LC_ALL": "C",
}
CHANGELOG = "# Changelog\n\n## 0.2.0 (2026-10-06)\n\n- old\n\n## 0.1.0\n\nFirst.\n"
HEADING = "## 0.3.0 (2026-10-09)\n\n"
SECTION = HEADING + "- eta one\n  eta continued\n- eta two\n- beta\n- alpha\n- zeta again\n"
STEPS = (
    "this script never stages, commits, tags, or pushes. the remaining steps:\n"
    "  git add CHANGELOG.md changes/\n"
    '  git commit -m "release 0.3.0"\n'
    '  git tag -a v0.3.0 -m "pstack-t3 0.3.0"    # on the commit that lands on main\n'
    "  git push origin v0.3.0\n"
    "  gh release create v0.3.0 --notes-file <release notes file>\n"
)
DRY_RUN = (
    SECTION
    + "\nwould write this section to CHANGELOG.md\n"
    "would delete changes/eta.md\nwould delete changes/beta.md\n"
    "would delete changes/alpha.md\nwould delete changes/zeta.md\n"
    "nothing changed\n" + STEPS
)
REAL_RUN = (
    SECTION
    + "\nwrote this section to CHANGELOG.md\n"
    "deleted changes/eta.md\ndeleted changes/beta.md\n"
    "deleted changes/alpha.md\ndeleted changes/zeta.md\n" + STEPS
)
RELEASED = " M CHANGELOG.md\n D changes/alpha.md\n D changes/beta.md\n D changes/eta.md\n D changes/zeta.md\n"
UNDO = "git restore --staged --worktree CHANGELOG.md changes/"
DIRTY = (
    "CHANGELOG.md or changes/ has uncommitted changes; commit them, "
    f"or run {UNDO} to undo an unfinished release:\n"
)
NOTHING_CHANGED = "; nothing changed, fix that and rerun"
NOT_A_BULLET = "is not a bullet or a continuation line; fix the fragment, commit it, and rerun\n"


def git(repo, *args, date=None):
    env = {**ENV, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date} if date else ENV
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True, encoding="utf-8", env=env
    ).stdout


def commit(repo, files, day=1, second=0):
    for relative, text in files.items():
        path = repo / relative
        if text is None:
            path.unlink()
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text if isinstance(text, bytes) else text.encode())
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "c", date=f"2026-01-{day:02d}T12:00:{second:02d}+00:00")


def run(repo, *args, env=ENV, date="2026-10-09"):
    outside_the_checkout = repo.parent
    return subprocess.run(
        [sys.executable, str(repo / "scripts/release.py"), *args, "--date", date],
        cwd=outside_the_checkout, capture_output=True, text=True, encoding="utf-8", env=env,
    )


def state(repo):
    paths = [repo / "CHANGELOG.md", *sorted((repo / "changes").rglob("*"))]
    files = {str(path.relative_to(repo)): path.read_bytes() for path in paths if path.is_file() and not path.is_symlink()}
    return git(repo, "status", "--porcelain", "--untracked-files=all"), git(repo, "rev-parse", "HEAD"), files


@contextmanager
def repository(changelog=CHANGELOG):
    with tempfile.TemporaryDirectory() as directory:
        repo = Path(directory) / "repo"
        repo.mkdir()
        git(repo, "init", "-q", "-b", "main")
        (repo / "scripts").mkdir()
        shutil.copy(ROOT / "scripts/release.py", repo / "scripts/release.py")
        commit(repo, {"CHANGELOG.md": changelog})
        yield repo


def add_fragments_out_of_name_and_date_order(repo):
    commit(repo, {"changes/zeta.md": "- zeta\n", "changes/eta.md": "- eta one\n  eta continued\n- eta two\n"}, day=2)
    commit(repo, {"changes/beta.md": "- beta\n"}, day=3)
    commit(repo, {"changes/alpha.md": "- alpha\n"}, day=3)
    commit(repo, {"changes/zeta.md": None}, day=4)
    git(repo, "commit", "-q", "--allow-empty", "-m", "spacer", date="2026-01-05T12:00:00+00:00")
    (repo / "changes/zeta.md").write_text("- zeta again\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "c", date="2025-12-01T12:00:00+00:00")


@contextmanager
def history():
    with repository() as repo:
        add_fragments_out_of_name_and_date_order(repo)
        yield repo


@contextmanager
def recording_handlers():
    """Stand in for the default handlers, so a signal the script fails to hold cannot kill the test run."""
    missed = []
    previous = {number: signal.signal(number, lambda signum, frame: missed.append(signum)) for number in release.HELD}
    try:
        yield missed
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


class ReleaseCase(unittest.TestCase):
    maxDiff = None

    def assert_refuses(self, repo, version, message):
        before = state(repo)
        result = run(repo, version)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (1, "", message))
        self.assertEqual(state(repo), before)

    def assert_section(self, repo, section):
        result = run(repo, "0.3.0", "--dry-run")
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        self.assertEqual(result.stdout[: len(section) + 1], section + "\n")


class RunTest(ReleaseCase):
    def test_dry_run_prints_the_section_and_changes_nothing(self):
        with history() as repo:
            before = state(repo)
            result = run(repo, "0.3.0", "--dry-run")
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, DRY_RUN, ""))
            self.assertEqual(state(repo), before)
            self.assertEqual(before[0], "")
            self.assertEqual((repo / "CHANGELOG.md").read_text(), CHANGELOG)
            self.assertEqual(sorted(path.name for path in (repo / "changes").iterdir()),
                             ["alpha.md", "beta.md", "eta.md", "zeta.md"])

    def test_dry_run_takes_the_flag_before_the_version(self):
        with history() as repo:
            result = run(repo, "--dry-run", "0.3.0")
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, DRY_RUN, ""))

    def test_release_writes_the_section_above_the_latest_heading(self):
        with history() as repo:
            result = run(repo, "0.3.0")
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, REAL_RUN, ""))
            self.assertEqual(
                (repo / "CHANGELOG.md").read_text(),
                "# Changelog\n\n" + SECTION + "\n## 0.2.0 (2026-10-06)\n\n- old\n\n## 0.1.0\n\nFirst.\n",
            )

    def test_release_deletes_the_fragments_and_leaves_git_alone(self):
        with history() as repo:
            head = git(repo, "rev-parse", "HEAD")
            self.assertEqual(run(repo, "0.3.0").returncode, 0)
            self.assertEqual(git(repo, "status", "--porcelain"), RELEASED)
            self.assertEqual(list((repo / "changes").iterdir()), [])
            self.assertEqual(git(repo, "diff", "--cached", "--name-only"), "")
            self.assertEqual(git(repo, "tag"), "")
            self.assertEqual(git(repo, "rev-parse", "HEAD"), head)

    def test_release_prints_the_remaining_steps(self):
        with history() as repo:
            self.assertEqual(run(repo, "0.3.0").stdout[-len(STEPS):], STEPS)

    def test_printed_git_add_stages_the_release(self):
        with history() as repo:
            printed = [line.strip() for line in run(repo, "0.3.0").stdout.splitlines()]
            add = [line for line in printed if line.startswith("git add ")]
            self.assertEqual(add, ["git add CHANGELOG.md changes/"])
            subprocess.run(shlex.split(add[0]), cwd=repo, check=True, env=ENV)
            self.assertEqual(
                git(repo, "status", "--porcelain"),
                "M  CHANGELOG.md\nD  changes/alpha.md\nD  changes/beta.md\nD  changes/eta.md\nD  changes/zeta.md\n",
            )

    def test_real_run_calls_only_read_only_git_and_never_gh(self):
        with history() as repo:
            shim = repo.parent / "shim"
            shim.mkdir()
            calls = repo.parent / "calls"
            for name in ("git", "gh"):
                real = shutil.which(name) or "/bin/true"
                (shim / name).write_text(f'#!/bin/sh\necho "{name} $1" >> "{calls}"\nexec "{real}" "$@"\n')
                (shim / name).chmod(0o755)
            result = run(repo, "0.3.0", env={**ENV, "PATH": f"{shim}{os.pathsep}{ENV['PATH']}"})
            self.assertEqual((result.returncode, result.stdout), (0, REAL_RUN))
            self.assertEqual(calls.read_text(), "git rev-parse\ngit status\ngit log\n")

    def test_changelog_without_a_heading_takes_the_section_at_the_end(self):
        with repository("# Changelog\n") as repo:
            commit(repo, {"changes/a.md": "- a\n"}, day=2)
            self.assertEqual(run(repo, "0.3.0").returncode, 0)
            self.assertEqual((repo / "CHANGELOG.md").read_text(), "# Changelog\n\n" + HEADING + "- a\n")

    def test_rerun_refuses_then_restore_recovers(self):
        with history() as repo:
            self.assertEqual(run(repo, "0.3.0").returncode, 0)
            self.assert_refuses(repo, "0.3.0", DIRTY + RELEASED)
            git(repo, *shlex.split(UNDO)[1:])
            self.assertEqual(git(repo, "status", "--porcelain"), "")
            self.assert_section(repo, SECTION)
            self.assertEqual(run(repo, "0.3.0").returncode, 0)
            git(repo, "add", "CHANGELOG.md", "changes/")
            git(repo, "commit", "-q", "-m", "release 0.3.0")
            self.assert_refuses(repo, "0.3.0", "CHANGELOG.md already has a ## 0.3.0 heading; pick the next version\n")

    def test_printed_undo_restores_a_staged_release(self):
        with history() as repo:
            before = state(repo)
            self.assertEqual(run(repo, "0.3.0").returncode, 0)
            git(repo, "add", "CHANGELOG.md", "changes/")
            self.assertEqual(git(repo, "status", "--porcelain"), "M  CHANGELOG.md\nD  changes/alpha.md\n"
                             "D  changes/beta.md\nD  changes/eta.md\nD  changes/zeta.md\n")
            git(repo, *shlex.split(UNDO)[1:])
            self.assertEqual(state(repo), before)

    def test_printed_undo_restores_an_unstaged_release(self):
        with history() as repo:
            before = state(repo)
            self.assertEqual(run(repo, "0.3.0").returncode, 0)
            git(repo, *shlex.split(UNDO)[1:])
            self.assertEqual(state(repo), before)

    def test_changelog_keeps_its_file_mode(self):
        with history() as repo:
            (repo / "CHANGELOG.md").chmod(0o640)
            self.assertEqual(run(repo, "0.3.0").returncode, 0)
            self.assertEqual((repo / "CHANGELOG.md").stat().st_mode & 0o777, 0o640)
            self.assertEqual([path.name for path in repo.glob(".*.tmp")], [])

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root deletes from a read-only directory")
    def test_failed_first_delete_leaves_the_files_as_they_were(self):
        with history() as repo:
            before = state(repo)
            (repo / "changes").chmod(0o555)
            try:
                result = run(repo, "0.3.0")
            finally:
                (repo / "changes").chmod(0o755)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stderr[:17], "stopped partway: ")
            self.assertEqual(result.stderr[-len(NOTHING_CHANGED) - 1:], NOTHING_CHANGED + "\n")
            self.assertEqual(state(repo), before)
            self.assertEqual(git(repo, "status", "--porcelain"), "")
            self.assertEqual(list(repo.glob(".*.tmp")), [])
            self.assert_section(repo, SECTION)

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root writes into a read-only directory")
    def test_failed_changelog_write_leaves_the_files_as_they_were(self):
        with history() as repo:
            before = state(repo)
            repo.chmod(0o555)
            try:
                result = run(repo, "0.3.0")
            finally:
                repo.chmod(0o755)
            self.assertEqual((result.returncode, result.stderr[:17]), (1, "stopped partway: "))
            self.assertEqual(result.stderr[-len(NOTHING_CHANGED) - 1:], NOTHING_CHANGED + "\n")
            self.assertEqual(state(repo), before)

    def apply_failing_at(self, repo, fail, restore=None):
        real_unlink, real_write, calls = pathlib.Path.unlink, release.write_file, []

        def unlink(path, *args, **kwargs):
            calls.append(path.name)
            if len(calls) == fail:
                raise PermissionError(13, "Permission denied", str(path))
            return real_unlink(path, *args, **kwargs)

        def write_file(path, data, mode):
            if restore and path.parent.name == "changes":
                raise OSError(28, "No space left on device", str(path))
            return real_write(path, data, mode)

        with mock.patch.object(release, "ROOT", repo):
            cut = release.plan("0.3.0", "2026-10-09")
            with mock.patch.object(pathlib.Path, "unlink", unlink), mock.patch.object(release, "write_file", write_file):
                with self.assertRaises(SystemExit) as raised:
                    release.apply(cut)
        return str(raised.exception), calls

    def test_failed_later_delete_puts_back_the_changelog_and_the_deleted_fragments(self):
        with history() as repo:
            before = state(repo)
            message, calls = self.apply_failing_at(repo, fail=3)
            self.assertEqual(calls, ["eta.md", "beta.md", "alpha.md"])
            self.assertEqual(message[:17], "stopped partway: ")
            self.assertEqual(message[-len(NOTHING_CHANGED):], NOTHING_CHANGED)
            self.assertEqual(state(repo), before)
            self.assertEqual(list(repo.glob(".*.tmp")) + list((repo / "changes").glob(".*.tmp")), [])

    def test_failed_last_delete_puts_everything_back(self):
        with history() as repo:
            before = state(repo)
            message, calls = self.apply_failing_at(repo, fail=4)
            self.assertEqual(calls, ["eta.md", "beta.md", "alpha.md", "zeta.md"])
            self.assertEqual(message[-len(NOTHING_CHANGED):], NOTHING_CHANGED)
            self.assertEqual(state(repo), before)

    def test_interrupt_puts_everything_back(self):
        with history() as repo:
            before = state(repo)
            real_unlink, calls = pathlib.Path.unlink, []

            def unlink(path, *args, **kwargs):
                calls.append(path.name)
                if len(calls) == 2:
                    raise KeyboardInterrupt
                return real_unlink(path, *args, **kwargs)

            with mock.patch.object(release, "ROOT", repo):
                cut = release.plan("0.3.0", "2026-10-09")
                with mock.patch.object(pathlib.Path, "unlink", unlink):
                    with self.assertRaises(SystemExit) as raised:
                        release.apply(cut)
            self.assertEqual(str(raised.exception), "stopped partway: interrupted" + NOTHING_CHANGED)
            self.assertEqual(state(repo), before)

    def apply_signalled(self, repo, replace=None, unlink=None, fail_unlink=None):
        """Run release.apply, sending each listed real signal right after the Nth os.replace or Path.unlink returns."""
        replace, unlink, calls = replace or {}, unlink or {}, {"replace": 0, "unlink": 0}
        real_replace, real_unlink = os.replace, pathlib.Path.unlink

        def after(kind, signals):
            calls[kind] += 1
            for number in signals.get(calls[kind], ()):
                os.kill(os.getpid(), number)

        def replacing(source, target, *args, **kwargs):
            real_replace(source, target, *args, **kwargs)
            after("replace", replace)

        def unlinking(path, *args, **kwargs):
            if calls["unlink"] + 1 == fail_unlink:
                calls["unlink"] += 1
                raise PermissionError(13, "Permission denied", str(path))
            real_unlink(path, *args, **kwargs)
            after("unlink", unlink)

        held = {number: signal.getsignal(number) for number in release.HELD}
        with recording_handlers() as missed, mock.patch.object(release, "ROOT", repo):
            cut = release.plan("0.3.0", "2026-10-09")
            with mock.patch.object(os, "replace", replacing), mock.patch.object(pathlib.Path, "unlink", unlinking):
                with self.assertRaises(SystemExit) as raised:
                    release.apply(cut)
            self.assertEqual(missed, [])
        self.assertEqual(held, {number: signal.getsignal(number) for number in release.HELD})
        return str(raised.exception)

    def test_signal_right_after_the_changelog_replace_puts_everything_back(self):
        for number in release.HELD:
            with self.subTest(signal=number), history() as repo:
                before = state(repo)
                message = self.apply_signalled(repo, replace={1: [number]})
                self.assertEqual(message, "stopped partway: interrupted" + NOTHING_CHANGED)
                self.assertEqual(state(repo), before)
                self.assertEqual(list(repo.glob(".*.tmp")) + list((repo / "changes").glob(".*.tmp")), [])

    def test_signal_right_after_each_fragment_delete_puts_everything_back(self):
        for call in (1, 2, 3, 4):
            for number in release.HELD:
                with self.subTest(delete=call, signal=number), history() as repo:
                    before = state(repo)
                    message = self.apply_signalled(repo, unlink={call: [number]})
                    self.assertEqual(message, "stopped partway: interrupted" + NOTHING_CHANGED)
                    self.assertEqual(state(repo), before)

    def test_repeated_signals_during_the_put_back_do_not_stop_it(self):
        with history() as repo:
            before = state(repo)
            message = self.apply_signalled(
                repo, fail_unlink=3, replace={2: [signal.SIGINT], 3: [signal.SIGTERM], 4: [signal.SIGHUP]})
            self.assertEqual(message[:17], "stopped partway: ")
            self.assertEqual(message[-len(NOTHING_CHANGED):], NOTHING_CHANGED)
            self.assertEqual(state(repo), before)

    def test_signal_then_more_signals_during_the_put_back_do_not_stop_it(self):
        with history() as repo:
            before = state(repo)
            message = self.apply_signalled(
                repo, unlink={2: [signal.SIGINT]}, replace={2: [signal.SIGINT, signal.SIGINT], 3: [signal.SIGTERM]})
            self.assertEqual(message, "stopped partway: interrupted" + NOTHING_CHANGED)
            self.assertEqual(state(repo), before)

    def test_signal_during_a_put_back_that_fails_still_names_the_files(self):
        with history() as repo:
            real_write = release.write_file

            def write_file(path, data, mode):
                if path.parent.name == "changes":
                    os.kill(os.getpid(), signal.SIGINT)
                    raise OSError(28, "No space left on device", str(path))
                return real_write(path, data, mode)

            with mock.patch.object(release, "write_file", write_file):
                message = self.apply_signalled(repo, unlink={2: [signal.SIGTERM]})
            self.assertIn("stopped partway: interrupted; could not put back changes/eta.md ([Errno 28]", message)
            self.assertIn(", changes/beta.md ([Errno 28]", message)
            self.assertEqual(message[-len(f"; run {UNDO} to undo, then rerun"):], f"; run {UNDO} to undo, then rerun")
            self.assertEqual((repo / "CHANGELOG.md").read_text(), CHANGELOG)
            git(repo, *shlex.split(UNDO)[1:])
            self.assertEqual(git(repo, "status", "--porcelain"), "")

    def test_a_signal_at_any_line_of_apply_leaves_the_files_as_they_were_or_released(self):
        for fail in (None, 3):
            with self.subTest(failing_delete=fail), history() as repo, mock.patch.object(release, "ROOT", repo):
                before, cut = state(repo), release.plan("0.3.0", "2026-10-09")
                real_unlink = pathlib.Path.unlink

                def run_traced(fire_at):
                    seen, deletes = 0, 0

                    def unlink(path, *args, **kwargs):
                        nonlocal deletes
                        deletes += 1
                        if deletes == fail:
                            raise PermissionError(13, "Permission denied", str(path))
                        return real_unlink(path, *args, **kwargs)

                    def local(frame, event, arg):
                        nonlocal seen
                        if event == "line":
                            seen += 1
                            if seen == fire_at:
                                sys.settrace(None)
                                os.kill(os.getpid(), signal.SIGINT)
                        return local

                    def tracer(frame, event, arg):
                        return local if frame.f_code.co_filename == release.__file__ else None

                    message = None
                    with mock.patch.object(pathlib.Path, "unlink", unlink):
                        sys.settrace(tracer)
                        try:
                            release.apply(cut)
                        except SystemExit as error:
                            message = str(error)
                        finally:
                            sys.settrace(None)
                    return seen, message

                with recording_handlers():
                    held = {number: signal.getsignal(number) for number in release.HELD}
                    lines, message = run_traced(0)
                    released = state(repo)
                    self.assertEqual(message is None, fail is None)
                    self.assertGreater(lines, 20)
                    outcomes = set()
                    for fire_at in range(1, lines + 1):
                        git(repo, *shlex.split(UNDO)[1:])
                        self.assertEqual(state(repo), before)
                        _, message = run_traced(fire_at)
                        self.assertEqual({n: signal.getsignal(n) for n in release.HELD}, held)
                        if message is None:
                            self.assertEqual(state(repo), released, f"signal at line event {fire_at}")
                            outcomes.add("released")
                        else:
                            self.assertEqual(message[:17], "stopped partway: ", f"signal at line event {fire_at}")
                            self.assertEqual(message[-len(NOTHING_CHANGED):], NOTHING_CHANGED)
                            self.assertEqual(state(repo), before, f"signal at line event {fire_at}")
                            outcomes.add("put back")
                    self.assertEqual(outcomes, {"released", "put back"} if fail is None else {"put back"})

    def test_failed_put_back_names_each_file_and_the_undo(self):
        with history() as repo:
            message, _ = self.apply_failing_at(repo, fail=3, restore=True)
            self.assertEqual(message[:17], "stopped partway: ")
            self.assertIn("; could not put back changes/eta.md ([Errno 28] No space left on device: ", message)
            self.assertIn(", changes/beta.md ([Errno 28]", message)
            self.assertNotIn("CHANGELOG.md (", message)
            self.assertEqual(message[-len(f"; run {UNDO} to undo, then rerun"):], f"; run {UNDO} to undo, then rerun")
            self.assertEqual((repo / "CHANGELOG.md").read_text(), CHANGELOG)
            git(repo, *shlex.split(UNDO)[1:])
            self.assertEqual(git(repo, "status", "--porcelain"), "")


class OrderTest(ReleaseCase):
    def test_order_matches_the_documented_log(self):
        with history() as repo:
            self.assertEqual(SECTION, HEADING + "\n".join(test_pstack_t3.release_bullets(repo)) + "\n")
            self.assert_section(repo, SECTION)

    def test_one_commit_orders_by_name_whatever_git_prints(self):
        with repository() as repo:
            (repo / "order").write_text("changes/c.md\n")
            git(repo, "config", "diff.orderFile", "order")
            commit(repo, {"changes/b.md": "- b\n", "changes/a.md": "- a\n", "changes/c.md": "- c\n"}, day=2)
            self.assertEqual(git(repo, *release.LOG), "\x01\0\nchanges/c.md\0changes/a.md\0changes/b.md\0")
            self.assert_section(repo, HEADING + "- a\n- b\n- c\n")

    def test_same_second_commits_keep_commit_order(self):
        with repository() as repo:
            commit(repo, {"changes/b.md": "- b\n"}, day=2)
            commit(repo, {"changes/a.md": "- a\n"}, day=2)
            self.assert_section(repo, HEADING + "- b\n- a\n")

    def test_an_earlier_dated_later_commit_keeps_commit_order(self):
        with repository() as repo:
            commit(repo, {"changes/a.md": "- a\n"}, day=9)
            commit(repo, {"changes/b.md": "- b\n"}, day=2)
            commit(repo, {"changes/c.md": "- c\n"}, day=5)
            self.assert_section(repo, HEADING + "- a\n- b\n- c\n")

    def test_renamed_fragment_orders_at_the_rename(self):
        with repository() as repo:
            commit(repo, {"changes/old.md": "- old\n"}, day=2)
            commit(repo, {"changes/mid.md": "- mid\n"}, day=3)
            git(repo, "mv", "changes/old.md", "changes/new.md")
            git(repo, "commit", "-q", "-m", "mv", date="2026-01-04T12:00:00+00:00")
            self.assert_section(repo, HEADING + "- mid\n- old\n")

    def test_non_ascii_fragment_name(self):
        with repository() as repo:
            commit(repo, {"changes/café.md": "- café\n"}, day=2)
            commit(repo, {"changes/a.md": "- a\n"}, day=3)
            self.assert_section(repo, HEADING + "- café\n- a\n")

    def test_edited_fragment_keeps_the_order_of_its_add(self):
        with repository() as repo:
            commit(repo, {"changes/b.md": "- b\n"}, day=2)
            commit(repo, {"changes/a.md": "- a\n"}, day=3)
            commit(repo, {"changes/b.md": "- b\n- b again\n"}, day=4)
            self.assert_section(repo, HEADING + "- b\n- b again\n- a\n")

    def test_git_log_record_shape(self):
        with repository() as repo:
            commit(repo, {"changes/z.md": "- z\n", "changes/a.md": "- a\n", "other": "x\n"}, day=2)
            commit(repo, {"other": "y\n"}, day=3)
            commit(repo, {"changes/b.md": "- b\n"}, day=4)
            self.assertEqual(git(repo, *release.LOG), "\x01\0\nchanges/a.md\0changes/z.md\0\x01\0\nchanges/b.md\0")

    @unittest.skipUnless(shutil.which("ssh-keygen"), "needs ssh-keygen to sign a commit")
    def test_signed_commits_keep_commit_order_with_show_signature_on(self):
        with repository() as repo:
            key = repo.parent / "key"
            subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
            git(repo, "config", "gpg.format", "ssh")
            git(repo, "config", "user.signingkey", f"{key}.pub")
            git(repo, "config", "commit.gpgsign", "true")
            git(repo, "config", "log.showSignature", "true")
            commit(repo, {"changes/b.md": "- b\n"}, day=2)
            commit(repo, {"changes/a.md": "- a\n"}, day=3)
            self.assertIn("-----BEGIN SSH SIGNATURE-----", git(repo, "cat-file", "commit", "HEAD"))
            self.assert_section(repo, HEADING + "- b\n- a\n")

    def test_added_at(self):
        self.assertEqual(release.added_at(""), {})
        self.assertEqual(
            release.added_at("\x01\0\nchanges/a.md\0changes/z.md\0\x01\0\nchanges/b.md\0"),
            {"a.md": 1, "z.md": 1, "b.md": 2},
        )
        self.assertEqual(
            release.added_at("\x01\0\nchanges/a.md\0\x01\0\nchanges/nested/x.md\0\x01\0\x01\0\nchanges/a.md\0"),
            {"a.md": 4},
        )
        for log in ("No signature\n\x01\0\nchanges/a.md\0", "changes/a.md\0", "\x01\0\nother/a.md\0"):
            with self.subTest(log=log), self.assertRaises(ValueError):
                release.added_at(log)


class RefusalTest(ReleaseCase):
    def test_refuses_bad_version(self):
        with history() as repo:
            for version in ("v0.3.0", "0.3", "0.03.0", "0.3.0-rc1", "0.3.0.1", "٠.٣.٠"):
                with self.subTest(version=version):
                    self.assert_refuses(
                        repo, version, f"version {version} is not X.Y.Z; pass three numbers such as 0.3.0\n"
                    )

    def test_refuses_bad_date(self):
        with history() as repo:
            for date in ("2026-02-30", "20261009", "10/09/2026"):
                with self.subTest(date=date):
                    before = state(repo)
                    result = run(repo, "0.3.0", date=date)
                    self.assertEqual(
                        (result.returncode, result.stdout, result.stderr),
                        (1, "", f"date {date} is not YYYY-MM-DD; pass a real date such as 2026-10-09\n"),
                    )
                    self.assertEqual(state(repo), before)

    def test_refuses_outside_a_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            (repo / "scripts").mkdir(parents=True)
            shutil.copy(ROOT / "scripts/release.py", repo / "scripts/release.py")
            (repo / "CHANGELOG.md").write_text(CHANGELOG)
            (repo / "changes").mkdir()
            (repo / "changes/a.md").write_text("- a\n")
            empty = Path(directory) / "empty"
            empty.mkdir()
            cases = {
                "no repository": ({**ENV, "GIT_CEILING_DIRECTORIES": directory}, "git rev-parse failed: fatal: not a git repository"),
                "no git": ({**ENV, "PATH": str(empty)}, "git rev-parse failed: [Errno 2] No such file or directory: 'git'"),
            }
            for name, (env, message) in cases.items():
                with self.subTest(name):
                    result = run(repo, "0.3.0", env=env)
                    self.assertEqual((result.returncode, result.stdout), (1, ""))
                    self.assertEqual(result.stderr[: len(message)], message)
                    self.assertEqual((repo / "CHANGELOG.md").read_text(), CHANGELOG)
                    self.assertEqual((repo / "changes/a.md").read_text(), "- a\n")

    def test_refuses_shallow_clone(self):
        with history() as repo:
            clone = repo.parent / "clone" / "repo"
            git(repo.parent, "clone", "-q", "--depth", "1", repo.as_uri(), str(clone))
            self.assert_refuses(
                clone, "0.3.0",
                "this clone is shallow, so git cannot tell when each fragment was added; "
                "run git fetch --unshallow and rerun\n",
            )

    def test_refuses_uncommitted_changes(self):
        def untracked(repo):
            (repo / "changes/new.md").write_text("- new\n")

        def modified(repo):
            (repo / "changes/beta.md").write_text("- beta, edited\n")

        def staged(repo):
            modified(repo)
            git(repo, "add", "changes/beta.md")

        def deleted(repo):
            (repo / "changes/beta.md").unlink()

        def changelog(repo):
            (repo / "CHANGELOG.md").write_text(CHANGELOG + "\nMore.\n")

        cases = (
            (untracked, "?? changes/new.md\n"),
            (modified, " M changes/beta.md\n"),
            (staged, "M  changes/beta.md\n"),
            (deleted, " D changes/beta.md\n"),
            (changelog, " M CHANGELOG.md\n"),
        )
        for change, status in cases:
            with self.subTest(change.__name__), history() as repo:
                change(repo)
                self.assert_refuses(repo, "0.3.0", DIRTY + status)

    def test_uncommitted_changes_elsewhere_do_not_refuse(self):
        with history() as repo:
            (repo / "notes.txt").write_text("unrelated\n")
            self.assert_section(repo, SECTION)

    def test_refuses_a_symlinked_changelog(self):
        with repository() as repo:
            commit(repo, {"changes/a.md": "- a\n", "real.md": CHANGELOG}, day=2)
            (repo / "CHANGELOG.md").unlink()
            (repo / "CHANGELOG.md").symlink_to("real.md")
            git(repo, "add", "-A")
            git(repo, "commit", "-q", "-m", "link", date="2026-01-03T12:00:00+00:00")
            self.assert_refuses(repo, "0.3.0", "CHANGELOG.md is a symlink; replace it with the file before you release\n")

    def test_refuses_existing_heading(self):
        with history() as repo:
            self.assert_refuses(repo, "0.2.0", "CHANGELOG.md already has a ## 0.2.0 heading; pick the next version\n")
            self.assert_refuses(repo, "0.1.0", "CHANGELOG.md already has a ## 0.1.0 heading; pick the next version\n")

    def test_refuses_a_garbage_dated_duplicate_heading(self):
        with repository("# Changelog\n\n## 0.3.0 (tomorrow)\n\n- draft\n\n## 0.2.0 (2026-10-06)\n\n- old\n") as repo:
            commit(repo, {"changes/a.md": "- a\n"}, day=2)
            self.assert_refuses(repo, "0.3.0", "CHANGELOG.md already has a ## 0.3.0 heading; pick the next version\n")
            self.assert_refuses(
                repo, "0.2.5",
                "0.2.5 is not above 0.3.0, the latest version in CHANGELOG.md; pick a higher version\n",
            )

    def test_refuses_version_not_above_latest(self):
        with history() as repo:
            self.assert_refuses(
                repo, "0.1.5",
                "0.1.5 is not above 0.2.0, the latest version in CHANGELOG.md; pick a higher version\n",
            )
        with repository("# Changelog\n\n## 0.2.0\n\n- backport\n\n## 0.9.0 (2026-10-06)\n\n- old\n") as repo:
            commit(repo, {"changes/a.md": "- a\n"}, day=2)
            self.assert_refuses(
                repo, "0.3.0",
                "0.3.0 is not above 0.9.0, the latest version in CHANGELOG.md; pick a higher version\n",
            )
            result = run(repo, "0.10.0", "--dry-run")
            self.assertEqual((result.returncode, result.stdout[:23]), (0, "## 0.10.0 (2026-10-09)\n"))

    def test_refuses_without_fragments(self):
        message = "changes/ holds no fragments; there is nothing to release\n"
        with repository() as repo:
            self.assert_refuses(repo, "0.3.0", message)
            (repo / "changes").mkdir()
            self.assert_refuses(repo, "0.3.0", message)

    def test_refuses_a_non_md_entry(self):
        def nested(repo):
            commit(repo, {"changes/nested/x.md": "- x\n"}, day=3)

        def text(repo):
            commit(repo, {"changes/notes.txt": "- notes\n"}, day=3)

        def link(repo):
            (repo / "changes/link.md").symlink_to("a.md")
            commit(repo, {}, day=3)

        for change, name in ((nested, "nested"), (text, "notes.txt"), (link, "link.md")):
            with self.subTest(name), repository() as repo:
                commit(repo, {"changes/a.md": "- a\n"}, day=2)
                change(repo)
                self.assert_refuses(
                    repo, "0.3.0",
                    f"changes/{name} is not a fragment; changes/ holds only .md files, so move or delete it\n",
                )

    def test_ignored_non_fragment_gitkeep(self):
        with repository() as repo:
            commit(repo, {"changes/a.md": "- a\n"}, day=2)
            (repo / ".git/info/exclude").write_text("changes/.gitkeep\n")
            (repo / "changes/.gitkeep").write_text("")
            self.assertEqual(git(repo, "status", "--porcelain", "--untracked-files=all"), "")
            self.assert_refuses(
                repo, "0.3.0",
                "changes/.gitkeep is not a fragment; changes/ holds only .md files, so move or delete it\n",
            )

    def test_refuses_line_that_is_not_a_bullet(self):
        cases = (
            ("- ok\nprose\n", "line 2 " + NOT_A_BULLET),
            ("- ok\n\n- two\n", "line 2 " + NOT_A_BULLET),
            ("- ok\n\n", "line 2 " + NOT_A_BULLET),
            ("  indented\n", "line 1 " + NOT_A_BULLET),
            ("", "holds no bullet; fix the fragment, commit it, and rerun\n"),
        )
        for text, message in cases:
            with self.subTest(text=text), repository() as repo:
                commit(repo, {"changes/a.md": "- a\n", "changes/note.md": text}, day=2)
                self.assert_refuses(repo, "0.3.0", "changes/note.md " + message)

    def test_refuses_a_fragment_with_cr(self):
        for text in (b"- ok\r\n- two\r\n", b"- ok\rprose\n"):
            with self.subTest(text=text), repository() as repo:
                commit(repo, {"changes/note.md": text}, day=2)
                self.assert_refuses(repo, "0.3.0", "changes/note.md line 1 " + NOT_A_BULLET)

    def test_refuses_a_fragment_that_is_not_utf8(self):
        with repository() as repo:
            commit(repo, {"changes/note.md": b"- caf\xe9\n"}, day=2)
            self.assert_refuses(repo, "0.3.0", "changes/note.md is not UTF-8; fix it\n")

    def test_refuses_a_changelog_that_is_not_utf8(self):
        with repository() as repo:
            commit(repo, {"CHANGELOG.md": b"# Changelog\n\n- caf\xe9\n", "changes/a.md": "- a\n"}, day=2)
            self.assert_refuses(repo, "0.3.0", "CHANGELOG.md is not UTF-8; fix it\n")

    def test_refuses_ignored_fragment(self):
        with history() as repo:
            (repo / ".git/info/exclude").write_text("changes/local.md\n")
            (repo / "changes/local.md").write_text("- local\n")
            self.assertEqual(git(repo, "status", "--porcelain", "--untracked-files=all"), "")
            self.assert_refuses(
                repo, "0.3.0",
                "git log shows no commit that added changes/local.md; commit the fragment and rerun\n",
            )


class RuleTest(unittest.TestCase):
    def test_bullet_fault(self):
        line = "line {} is not a bullet or a continuation line".format
        cases = (
            (["- a"], None),
            (["- a", "  b"], None),
            (["- a", "\tb"], None),
            (["- a", "- b", "  c"], None),
            ([], "holds no bullet"),
            (["prose"], line(1)),
            (["- "], line(1)),
            (["-a"], line(1)),
            (["  b"], line(1)),
            (["- a", ""], line(2)),
            (["- a", "b"], line(2)),
            (["- a", "  "], line(2)),
            (["- a", "  b", "c"], line(3)),
        )
        for lines, fault in cases:
            with self.subTest(lines=lines):
                self.assertEqual(release.bullet_fault(lines), fault)
                self.assertEqual(test_pstack_t3.fragment_holds_bullets(lines), fault is None)
        self.assertEqual(release.bullet_fault(["- a\r"]), line(1))
        self.assertEqual(release.bullet_fault(["- a", "  b\r"]), line(2))

    def test_splice(self):
        section = "## 0.3.0 (2026-10-09)\n\n- a\n"
        cases = (
            ("# Changelog\n", "# Changelog\n\n" + section),
            ("", section),
            ("# C\n\n## 0.1.0\n", "# C\n\n" + section + "\n## 0.1.0\n"),
            ("# C\n\n## Unreleased\n\n## 0.1.0\n", "# C\n\n" + section + "\n## Unreleased\n\n## 0.1.0\n"),
            ("## 0.1.0\n\n- old\n", section + "\n## 0.1.0\n\n- old\n"),
        )
        for changelog, spliced in cases:
            with self.subTest(changelog=changelog):
                self.assertEqual(release.splice(changelog, section), spliced)

    def test_released(self):
        changelog = (
            "# Changelog\n\n## 0.3.0 (tomorrow)\n\n## Unreleased\n\n## 0.10.0 (2026-10-06)\n\n"
            "## 0.2.0-rc1\n\n### 0.4.0\n\n## 0.1.0\n\n- ## 9.9.9\n"
        )
        self.assertEqual(release.released(changelog), [(0, 3, 0), (0, 10, 0), (0, 1, 0)])
        self.assertEqual(release.released("# Changelog\n"), [])


if __name__ == "__main__":
    unittest.main()
