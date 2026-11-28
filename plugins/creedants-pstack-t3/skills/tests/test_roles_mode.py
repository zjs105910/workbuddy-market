import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "t3/scripts"))
sys.path.insert(0, str(ROOT / "t3/added/landing/scripts"))

import land  # noqa: E402
import roles  # noqa: E402
from tests.test_roles_cli import FOUR_PATHS, PLAYBOOK_NAMES, ROOT_ALIASES, Repo  # noqa: E402

LIGHT_USER = "Mode: light\nMode source: roles.json\n"
LIGHT_PROJECT = "Mode: light\nMode source: .pstack/t3-roles.json\n"
TRACKED = (
    "t3/added/landing/scripts/land.py",
    "t3/added/landing/SKILL.md",
    "db/migrations/0001.sql",
    "docs/migrations.md",
    "scripts/install.py",
)
CANONICAL_CORPUS = (
    "", ".", "/", " a/b ", "./a//b/", "a/../b", "/../x", "a\\b", "a/b/", "../x", "..", "a/../../x",
)
WAIVER_ROWS = {
    "feature": (
        ("Arena", "Interrogate", "Comment Sicko"),
        ("How", "Architect", "Arena", "Interrogate", "Comment Sicko"),
    ),
    "bug-fix": (
        ("Comment Sicko",),
        ("How", "Why", "Architect", "Comment Sicko"),
    ),
    "refactoring": (
        ("Comment Sicko",),
        ("How", "Architect", "Comment Sicko"),
    ),
    "perf-issue": (
        ("Comment Sicko",),
        ("How", "Architect", "Comment Sicko"),
    ),
    "hillclimb": (
        ("Comment Sicko",),
        ("How", "Comment Sicko"),
    ),
    "authoring-a-skill": (
        ("Comment Sicko", "Second-provider test"),
        ("Comment Sicko", "Second-provider test"),
    ),
}


def run_mode(directory, *args, env=None):
    base = {**os.environ, "XDG_CONFIG_HOME": str(directory)}
    if env:
        base.update(env)
    return subprocess.run(
        [sys.executable, str(ROOT / "t3/scripts/roles.py"), "mode", *args, "--cwd", str(directory)],
        env=base,
        capture_output=True,
        text=True,
    )


def escalated(path):
    return f"Mode: full\nMode source: escalated: lease covers {path}\n"


class GitRepo:
    def __init__(self, directory, tracked):
        self.directory = Path(directory)
        self.env = {
            **os.environ,
            "XDG_CONFIG_HOME": str(self.directory),
            "GIT_CEILING_DIRECTORIES": str(self.directory.resolve().parent),
        }
        subprocess.run(
            ["git", "init", "-q"], cwd=self.directory, env=self.env, check=True, capture_output=True,
        )
        for relative in tracked:
            path = self.directory / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("tracked\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", "--", relative],
                cwd=self.directory,
                env=self.env,
                check=True,
                capture_output=True,
            )
        self.project = self.directory / ".pstack" / "t3-roles.json"
        self.user = self.directory / "pstack-t3" / "roles.json"

    def put(self, path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    def run(self, *args, cwd=None):
        return subprocess.run(
            [sys.executable, str(ROOT / "t3/scripts/roles.py"), "mode", *args, "--cwd", str(cwd or self.directory)],
            env=self.env,
            capture_output=True,
            text=True,
        )


class ModeCommandTest(unittest.TestCase):
    def test_user_light_prints_roles_json(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Repo(directory)
            repo.put(repo.user, {"mode": "light"})
            completed = run_mode(directory)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, LIGHT_USER)

    def test_project_light_prints_project_label(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Repo(directory)
            repo.put(repo.project, {"mode": "light"})
            completed = run_mode(directory)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, LIGHT_PROJECT)

    def test_no_files_prints_default(self):
        with tempfile.TemporaryDirectory() as directory:
            Repo(directory)
            completed = run_mode(directory)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "Mode: full\nMode source: default\n")

    def test_coordinator_light_over_project_full(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Repo(directory)
            repo.put(repo.project, {"mode": "full"})
            completed = run_mode(directory, "--coordinator-mode", "light")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "Mode: light\nMode source: restaurant.json\n")

    def test_brief_full_over_project_light(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Repo(directory)
            repo.put(repo.project, {"mode": "light"})
            completed = run_mode(directory, "--brief-mode", "full")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "Mode: full\nMode source: brief\n")

    def test_session_light_over_project_full(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Repo(directory)
            repo.put(repo.project, {"mode": "full"})
            completed = run_mode(directory, "--session-mode", "light")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "Mode: light\nMode source: session\n")

    def test_brief_full_over_session_light(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Repo(directory)
            repo.put(repo.project, {"mode": "full"})
            completed = run_mode(directory, "--brief-mode", "full", "--session-mode", "light")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "Mode: full\nMode source: brief\n")

    def test_second_send_back_escalates(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Repo(directory)
            repo.put(repo.user, {"mode": "light"})
            completed = run_mode(directory, "--send-backs", "2")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "Mode: full\nMode source: escalated: second send-back\n")

    def test_first_send_back_stays_light(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Repo(directory)
            repo.put(repo.user, {"mode": "light"})
            completed = run_mode(directory, "--send-backs", "1")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, LIGHT_USER)

    def test_durable_reason_escalates(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Repo(directory)
            repo.put(repo.user, {"mode": "light"})
            completed = run_mode(directory, "--escalated", "lock order")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "Mode: full\nMode source: escalated: lock order\n")

    def test_durable_reason_wins_over_send_backs(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Repo(directory)
            repo.put(repo.user, {"mode": "light"})
            completed = run_mode(directory, "--escalated", "lock order", "--send-backs", "3")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "Mode: full\nMode source: escalated: lock order\n")

    def test_escalation_overrides_brief_light(self):
        with tempfile.TemporaryDirectory() as directory:
            Repo(directory)
            completed = run_mode(directory, "--brief-mode", "light", "--send-backs", "2")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "Mode: full\nMode source: escalated: second send-back\n")

    def test_empty_durable_reason_exits_1(self):
        with tempfile.TemporaryDirectory() as directory:
            Repo(directory)
            completed = run_mode(directory, "--escalated", "")
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(completed.stdout, "")
        self.assertEqual(completed.stderr, "error: --escalated needs a one-line reason\n")

    def test_durable_reason_with_a_break_exits_1(self):
        for text in ("\n", "lock\norder", "\r", "lock\rorder"):
            with self.subTest(text=text):
                with tempfile.TemporaryDirectory() as directory:
                    Repo(directory)
                    completed = run_mode(directory, "--escalated", text)
                self.assertEqual(completed.returncode, 1)
                self.assertEqual(completed.stdout, "")
                self.assertEqual(completed.stderr, "error: --escalated needs a one-line reason\n")

    def test_negative_send_backs_exits_2(self):
        with tempfile.TemporaryDirectory() as directory:
            Repo(directory)
            completed = run_mode(directory, "--send-backs", "-1")
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stdout, "")

    def open_tracked(self, directory, tracked=TRACKED, escalate=None):
        repo = GitRepo(directory, tracked)
        repo.put(repo.project, {"mode": "light", "escalate": list(FOUR_PATHS if escalate is None else escalate)})
        return repo

    def test_file_lease_equal_to_a_pattern_escalates(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = self.open_tracked(directory)
            completed = repo.run("--paths", "scripts/install.py")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, escalated("scripts/install.py"))

    def test_directory_lease_escalates_on_a_tracked_descendant(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = self.open_tracked(directory)
            completed = repo.run("--paths", "t3/added/landing")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, escalated("t3/added/landing/scripts/land.py"))

    def test_sibling_file_lease_stays_light(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = self.open_tracked(directory)
            completed = repo.run("--paths", "t3/added/landing/SKILL.md")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, LIGHT_PROJECT)

    def test_root_lease_escalates_on_the_first_tracked_match(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = self.open_tracked(directory)
            completed = repo.run("--paths", ".")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, escalated("db/migrations/0001.sql"))

    def test_double_star_matches_a_migrations_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = self.open_tracked(directory)
            completed = repo.run("--paths", "db")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, escalated("db/migrations/0001.sql"))

    def test_double_star_skips_a_migrations_file_name(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = self.open_tracked(directory)
            completed = repo.run("--paths", "docs/migrations.md")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, LIGHT_PROJECT)

    def test_untracked_file_lease_matches(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = self.open_tracked(directory)
            completed = repo.run("--paths", "t3/added/brigade/scripts/brigade.py")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, escalated("t3/added/brigade/scripts/brigade.py"))

    def test_star_does_not_cross_a_slash(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = self.open_tracked(
                directory,
                tracked=("scripts/tools/x.py", "scripts/install.py"),
                escalate=["scripts/*.py"],
            )
            nested = repo.run("--paths", "scripts/tools/x.py")
            direct = repo.run("--paths", "scripts/install.py")
        self.assertEqual(nested.returncode, 0, nested.stderr)
        self.assertEqual(nested.stdout, LIGHT_PROJECT)
        self.assertEqual(direct.returncode, 0, direct.stderr)
        self.assertEqual(direct.stdout, escalated("scripts/install.py"))

    def test_lease_leaving_the_repository_exits_1(self):
        with tempfile.TemporaryDirectory() as directory:
            Repo(directory)
            completed = run_mode(directory, "--paths", "../x")
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(completed.stdout, "")
        self.assertEqual(completed.stderr, "error: lease path '../x' leaves the repository\n")

    def test_lease_aliases_normalize(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = self.open_tracked(directory, tracked=(), escalate=["a/b", "b"])
            dotted = repo.run("--paths", "./a//b/")
            parent = repo.run("--paths", "a/../b")
        self.assertEqual(dotted.returncode, 0, dotted.stderr)
        self.assertEqual(dotted.stdout, escalated("a/b"))
        self.assertEqual(parent.returncode, 0, parent.stderr)
        self.assertEqual(parent.stdout, escalated("b"))

    def test_paths_without_an_escalate_list_skip_git(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Repo(directory)
            repo.put(repo.user, {"mode": "light"})
            completed = run_mode(directory, "--paths", "t3/added/landing")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, LIGHT_USER)

    def test_paths_outside_git_exit_2(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Repo(directory)
            repo.put(repo.project, {"mode": "light", "escalate": list(FOUR_PATHS)})
            completed = run_mode(directory, "--paths", "t3/added/landing")
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(
            completed.stderr,
            f"error: --paths needs a git checkout to list tracked files, and {directory} is not one\n",
        )

    def test_escalate_pattern_leaving_the_repository_exits_1(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Repo(directory)
            repo.put(repo.project, {"escalate": ["../x"]})
            completed = run_mode(directory)
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(completed.stdout, "")
        self.assertEqual(
            completed.stderr,
            f"error: {repo.project}: escalate pattern '../x' leaves the repository\n",
        )

    def test_root_normalized_escalate_patterns_keep_mode_resolution(self):
        for pattern in ROOT_ALIASES:
            with self.subTest(pattern=pattern):
                with tempfile.TemporaryDirectory() as directory:
                    repo = Repo(directory)
                    repo.put(repo.project, {"mode": "light", "escalate": [pattern]})
                    completed = run_mode(directory)
                self.assertEqual(completed.returncode, 0)
                self.assertEqual(completed.stdout, LIGHT_PROJECT)
                self.assertEqual(completed.stderr, "")

    def test_root_normalized_escalate_patterns_do_not_match_tracked_files(self):
        for pattern in ROOT_ALIASES:
            with self.subTest(pattern=pattern):
                with tempfile.TemporaryDirectory() as directory:
                    repo = GitRepo(directory, ("scripts/install.py",))
                    repo.put(repo.project, {"mode": "light", "escalate": [pattern]})
                    root = repo.run("--paths", ".")
                    tracked = repo.run("--paths", "scripts/install.py")
                for completed in (root, tracked):
                    self.assertEqual(completed.returncode, 0)
                    self.assertEqual(completed.stdout, LIGHT_PROJECT)
                    self.assertEqual(completed.stderr, "")

    def test_escalate_pattern_aliases_normalize_before_segment_matching(self):
        for pattern in (" ./scripts//install.py/ ", "scripts/old/../install.py", "scripts\\install.py"):
            with self.subTest(pattern=pattern):
                with tempfile.TemporaryDirectory() as directory:
                    repo = GitRepo(directory, ("scripts/install.py", "scripts/tools/install.py"))
                    repo.put(repo.project, {"mode": "light", "escalate": [pattern]})
                    completed = repo.run("--paths", "scripts/install.py")
                self.assertEqual(completed.returncode, 0)
                self.assertEqual(
                    completed.stdout,
                    "Mode: full\nMode source: escalated: lease covers scripts/install.py\n",
                )
                self.assertEqual(completed.stderr, "")
        with tempfile.TemporaryDirectory() as directory:
            repo = GitRepo(directory, ("scripts/install.py", "scripts/tools/install.py"))
            repo.put(repo.project, {"mode": "light", "escalate": [" ./scripts//*.py/ "]})
            completed = repo.run("--paths", "scripts/tools/install.py")
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, LIGHT_PROJECT)
        self.assertEqual(completed.stderr, "")

    def test_rule1_reads_root_from_subdirectory(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = self.open_tracked(directory)
            completed = repo.run("--paths", "t3/added/landing", cwd=repo.directory / "docs")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, escalated("t3/added/landing/scripts/land.py"))

    def test_rule1_stable_first_hit(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = self.open_tracked(
                directory,
                tracked=("b/risk.py", "a/risk.py"),
                escalate=["b/*.py", "a/*.py"],
            )
            completed = repo.run("--paths", ".")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, escalated("a/risk.py"))

    def test_bug_fix_fix_under_light_prints_waivers(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Repo(directory)
            repo.put(repo.user, {"mode": "light"})
            completed = run_mode(directory, "--playbook", "bug-fix", "--attempt", "fix")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            completed.stdout,
            "Playbook: playbooks/bug-fix.md\n"
            "Mode: light\n"
            "Mode source: roles.json\n"
            "Attempt: fix\n"
            "Waived by mode: How, Why, Architect, Comment Sicko\n",
        )

    def test_bug_fix_fix_under_full_prints_no_waivers(self):
        with tempfile.TemporaryDirectory() as directory:
            Repo(directory)
            completed = run_mode(directory, "--playbook", "bug-fix", "--attempt", "fix")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            completed.stdout,
            "Playbook: playbooks/bug-fix.md\nMode: full\nMode source: default\nAttempt: fix\n",
        )

    def test_feature_first_under_light(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Repo(directory)
            repo.put(repo.user, {"mode": "light"})
            completed = run_mode(directory, "--playbook", "feature", "--attempt", "first")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            completed.stdout.splitlines()[-1],
            "Waived by mode: Arena, Interrogate, Comment Sicko",
        )

    def test_escalated_fix_prints_no_waivers(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Repo(directory)
            repo.put(repo.user, {"mode": "light"})
            completed = run_mode(directory, "--playbook", "bug-fix", "--attempt", "fix", "--send-backs", "2")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            completed.stdout,
            "Playbook: playbooks/bug-fix.md\n"
            "Mode: full\n"
            "Mode source: escalated: second send-back\n"
            "Attempt: fix\n",
        )

    def test_playbook_without_a_row_prints_no_waiver_line(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Repo(directory)
            repo.put(repo.user, {"mode": "light"})
            completed = run_mode(directory, "--playbook", "investigation", "--attempt", "first")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            completed.stdout,
            "Playbook: playbooks/investigation.md\nMode: light\nMode source: roles.json\nAttempt: first\n",
        )

    def test_playbook_without_attempt_exits_1(self):
        with tempfile.TemporaryDirectory() as directory:
            Repo(directory)
            completed = run_mode(directory, "--playbook", "bug-fix")
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(completed.stderr, "error: --playbook and --attempt go together: pass both or neither\n")

    def test_attempt_without_playbook_exits_1(self):
        with tempfile.TemporaryDirectory() as directory:
            Repo(directory)
            completed = run_mode(directory, "--attempt", "fix")
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(completed.stderr, "error: --playbook and --attempt go together: pass both or neither\n")

    def test_unknown_playbook_exits_1(self):
        with tempfile.TemporaryDirectory() as directory:
            Repo(directory)
            completed = run_mode(directory, "--playbook", "bugfix", "--attempt", "fix")
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(
            completed.stderr,
            f"error: unknown playbook 'bugfix': expected one of: {PLAYBOOK_NAMES}\n",
        )

    def test_bad_attempt_exits_2(self):
        with tempfile.TemporaryDirectory() as directory:
            Repo(directory)
            completed = run_mode(directory, "--attempt", "retry")
        self.assertEqual(completed.returncode, 2)


class ModeFunctionTest(unittest.TestCase):
    def test_light_waivers_table(self):
        expected = {}
        for playbook, (first, retry) in WAIVER_ROWS.items():
            expected[(playbook, "first")] = first
            expected[(playbook, "fix")] = retry
            expected[(playbook, "bounce")] = retry
        self.assertEqual(dict(roles.LIGHT_WAIVERS), expected)
        self.assertEqual(list(roles.LIGHT_WAIVERS), list(expected))
        self.assertEqual(roles.LIGHT_WAIVERS[("investigation", "fix")], ())
        with self.assertRaises(KeyError):
            roles.LIGHT_WAIVERS[("feature", "retry")]

    def same_result(self, left, right, left_error, right_error, *args):
        try:
            left_value = left(*args)
            left_raised = None
        except left_error as error:
            left_value = None
            left_raised = error
        try:
            right_value = right(*args)
            right_raised = None
        except right_error as error:
            right_value = None
            right_raised = error
        if left_raised or right_raised:
            self.assertIsInstance(left_raised, left_error)
            self.assertIsInstance(right_raised, right_error)
            self.assertEqual(str(left_raised), str(right_raised))
        else:
            self.assertEqual(left_value, right_value)

    def test_canonical_matches_land(self):
        for path in CANONICAL_CORPUS:
            for kind in ("lease", "escalate pattern"):
                with self.subTest(path=path, kind=kind):
                    self.same_result(
                        roles.canonical, land.canonical, roles.ModeSettingsError, land.LandError, path, kind,
                    )
        for text in ("a,,b", "./a//b/,a/b", ""):
            with self.subTest(text=text):
                self.same_result(
                    roles.lease_paths, land.wanted_paths, roles.ModeSettingsError, land.LandError, text,
                )

    def test_canonical_literals(self):
        self.assertEqual(roles.canonical("./a//b/"), "a/b")
        self.assertEqual(roles.canonical("a/../b"), "b")
        self.assertEqual(roles.canonical("/../x"), "x")
        self.assertEqual(roles.canonical("."), "")

    def test_segments_match(self):
        self.assertTrue(roles.segments_match("**/migrations/**", "db/migrations/0001.sql"))
        self.assertFalse(roles.segments_match("**/migrations/**", "docs/migrations.md"))
        self.assertFalse(roles.segments_match("scripts/*.py", "scripts/tools/x.py"))
        self.assertTrue(roles.segments_match("**", ""))
