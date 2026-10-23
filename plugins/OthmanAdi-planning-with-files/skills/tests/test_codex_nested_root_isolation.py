"""Nested plan-root isolation for the Codex hook route (issue #212).

tests/test_nested_plan_isolation.py covers the canonical inject-plan.sh
dispatcher. This file covers the OTHER route with the same bug: the
independently written .codex/hooks.json integration, which is the route
Codex actually executes. Three semantics, ported from inject-plan.sh:

  * PWF_PLAN_ROOT — absolute plan-root binding, highest precedence.
    .codex/hooks/user-prompt-submit.sh prefixes every planning-state read
    with it, the shared resolver resolves under it, and the Python adapter
    (pre_tool_use / post_tool_use / stop / permission_request) routes its
    shell helpers and the session-attachment check through it. A broken pin
    fails CLOSED: the once-per-turn hook emits one notice, the per-tool-call
    hooks refuse silently.
  * Session-attachment notice — the guard itself predates this change; the
    refusal now announces itself (once per turn, user-prompt-submit only)
    with the same wording as inject-plan.sh.
  * Nested-root conflict detection — a cwd GUESS (active-plan pointer,
    newest-by-mtime, or legacy root task_plan.md) refuses to inject when a
    direct child of the effective root carries its own competing .planning.
    Explicit resolution (valid PLAN_ID, valid pin, attached session) skips
    the check.

Tree used throughout (the reporter's shape):

    workspace/.planning/plan-a            (active via .active_plan)
    workspace/project/.planning/plan-b    (active via its own .active_plan)
"""
from __future__ import annotations

import json
import hashlib
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
HOOKS_DIR = REPO_ROOT / ".codex" / "hooks"

PLAN_A_TITLE = "PLAN-ALPHA-PARENT-WORKSPACE"
PLAN_B_TITLE = "PLAN-BRAVO-NESTED-PROJECT"

SCRUB_VARS = (
    "PLAN_ID",
    "PWF_PLAN_ROOT",
    "PWF_SESSION_ID",
    "PWF_SESSION_KEY",
    "PWF_INJECT",
    "PLANNING_DISABLED",
)


def session_key(root: Path, session_id: str) -> str:
    digest = hashlib.sha256()
    project = os.path.normcase(os.path.realpath(os.path.abspath(root))).replace("\\", "/")
    for value in ("codex", project, session_id):
        encoded = value.encode("utf-8", errors="surrogatepass")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


def shell_and_env() -> tuple[str, dict[str, str]]:
    """POSIX sh, or the real Git-for-Windows sh plus its coreutils PATH."""
    env = os.environ.copy()
    env["PWF_TRUSTED_PYTHON"] = str(Path(sys.executable).resolve())
    if os.name != "nt":
        shell = shutil.which("sh")
        if shell is None:
            raise unittest.SkipTest("POSIX sh is unavailable")
        return shell, env

    sys.path.insert(0, str(HOOKS_DIR))
    try:
        import codex_hook_adapter as adapter

        shell, extra_path_dirs = adapter._windows_git_bash()
    finally:
        sys.path.pop(0)
    if shell is None:
        raise unittest.SkipTest("Git for Windows sh.exe is unavailable")
    if extra_path_dirs:
        env["PATH"] = os.pathsep.join([*extra_path_dirs, env.get("PATH", "")])
    return shell, env


class NestedTreeMixin(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="pwf-codex-nested-"))
        self.workspace = self.tmp / "workspace"
        self.project = self.workspace / "project"

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def build_tree(self, nested: bool = True, phased_nested: bool = False) -> None:
        plan_a = self.workspace / ".planning" / "plan-a"
        plan_a.mkdir(parents=True)
        (plan_a / "task_plan.md").write_text(f"# {PLAN_A_TITLE}\n", encoding="utf-8")
        (plan_a / "progress.md").write_text("# progress a\n", encoding="utf-8")
        (self.workspace / ".planning" / ".active_plan").write_text(
            "plan-a\n", encoding="utf-8"
        )
        if nested:
            plan_b = self.project / ".planning" / "plan-b"
            plan_b.mkdir(parents=True)
            body = f"# {PLAN_B_TITLE}\n"
            if phased_nested:
                body += "\n### Phase 1: Work\n- **Status:** in_progress\n"
            (plan_b / "task_plan.md").write_text(body, encoding="utf-8")
            (plan_b / "progress.md").write_text("# progress b\n", encoding="utf-8")
            (self.project / ".planning" / ".active_plan").write_text(
                "plan-b\n", encoding="utf-8"
            )


class CodexUserPromptSubmitNestedRootTests(NestedTreeMixin):
    """The once-per-turn shell hook: notices allowed, fail closed on ambiguity."""

    def _run(self, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        shell, env = shell_and_env()
        for var in SCRUB_VARS:
            env.pop(var, None)
        if env_extra:
            env.update(env_extra)
        return subprocess.run(
            [shell, str(HOOKS_DIR / "user-prompt-submit.sh")],
            cwd=str(self.workspace),
            text=True,
            encoding="utf-8",
            capture_output=True,
            env=env,
            check=False,
        )

    # -- 1. ambiguous parent cwd: fail closed ------------------------------
    def test_parent_cwd_with_nested_plan_injects_nothing(self) -> None:
        self.build_tree(nested=True)
        result = self._run()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertNotIn(PLAN_A_TITLE, result.stdout, "parent plan body must not inject")
        self.assertNotIn(PLAN_B_TITLE, result.stdout, "nested plan body must not inject")
        self.assertIn("Ambiguous plan", result.stdout)
        self.assertIn("project", result.stdout, "warning must name the nested root")
        self.assertIn("PWF_PLAN_ROOT", result.stdout)
        self.assertIn("PLAN_ID", result.stdout)

    # -- 2. PWF_PLAN_ROOT pins the nested project --------------------------
    def test_plan_root_pin_from_parent_cwd_injects_nested_plan(self) -> None:
        self.build_tree(nested=True)
        result = self._run({"PWF_PLAN_ROOT": str(self.project)})
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn(PLAN_B_TITLE, result.stdout, "pinned root's plan must inject")
        self.assertNotIn(PLAN_A_TITLE, result.stdout, "parent plan must not leak through")
        self.assertIn("ACTIVE PLAN", result.stdout)

    # -- 3. broken pin fails closed, never falls back ----------------------
    def test_plan_root_broken_pin_notices_and_injects_nothing(self) -> None:
        self.build_tree(nested=True)
        result = self._run({"PWF_PLAN_ROOT": str(self.workspace / "does-not-exist")})
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertNotEqual("", result.stdout.strip(), "broken pin must emit a notice")
        self.assertIn("PWF_PLAN_ROOT", result.stdout)
        self.assertNotIn(PLAN_A_TITLE, result.stdout, "must not fall back to cwd plan")
        self.assertNotIn(PLAN_B_TITLE, result.stdout)

    def test_relative_and_sibling_shell_pins_fail_closed(self) -> None:
        self.build_tree(nested=True)
        sibling = self.tmp / "sibling"
        sibling.mkdir()
        for pin in ("project", str(sibling)):
            with self.subTest(pin=pin):
                result = self._run({"PWF_PLAN_ROOT": pin})
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertIn("PWF_PLAN_ROOT", result.stdout)
                self.assertNotIn(PLAN_A_TITLE, result.stdout)
                self.assertNotIn(PLAN_B_TITLE, result.stdout)

    # -- 4. explicit PLAN_ID beats the conflict check ----------------------
    def test_valid_plan_id_at_parent_still_injects_despite_nested_plan(self) -> None:
        self.build_tree(nested=True)
        result = self._run({"PLAN_ID": "plan-a"})
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn(
            PLAN_A_TITLE,
            result.stdout,
            "explicit PLAN_ID names the plan deliberately; conflict check must not fire",
        )
        self.assertNotIn("Ambiguous plan", result.stdout)

    # -- 5. session guard now says why it refuses --------------------------
    def test_unattached_session_refuses_with_notice(self) -> None:
        self.build_tree(nested=False)
        (self.workspace / ".planning" / "sessions").mkdir()
        result = self._run({"PWF_SESSION_ID": "sess-1"})
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertNotIn(PLAN_A_TITLE, result.stdout)
        self.assertIn("Session isolation is armed", result.stdout)
        # The notice must name both recovery routes.
        self.assertIn("PWF_SESSION_ID", result.stdout)
        self.assertIn("delete", result.stdout)

    def test_sessions_dir_with_no_session_id_says_why(self) -> None:
        self.build_tree(nested=False)
        (self.workspace / ".planning" / "sessions").mkdir()
        result = self._run()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertNotIn(PLAN_A_TITLE, result.stdout)
        self.assertIn("Session isolation is armed", result.stdout)

    # -- 6. attachment does not choose between competing roots -------------
    def test_attached_session_does_not_bypass_conflict_check(self) -> None:
        self.build_tree(nested=True)
        sessions = self.workspace / ".planning" / "sessions"
        sessions.mkdir()
        (sessions / f"{session_key(self.workspace, 'sess-1')}.attached").write_text("", encoding="utf-8")
        result = self._run({"PWF_SESSION_ID": "sess-1"})
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertNotIn(PLAN_A_TITLE, result.stdout)
        self.assertNotIn(PLAN_B_TITLE, result.stdout)
        self.assertIn("Ambiguous plan", result.stdout)

    # -- 7. legacy invariant: no nesting = unchanged injection -------------
    def test_no_nested_plan_injects_exactly_as_before(self) -> None:
        self.build_tree(nested=False)
        result = self._run()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("ACTIVE PLAN", result.stdout)
        self.assertIn(PLAN_A_TITLE, result.stdout)
        self.assertNotIn("Ambiguous plan", result.stdout)
        self.assertNotIn("Session isolation", result.stdout)

    def test_bare_nested_planning_is_no_conflict(self) -> None:
        # A nested .planning without .active_plan and without any
        # <slug>/task_plan.md is not a competing plan.
        self.build_tree(nested=False)
        (self.project / ".planning").mkdir(parents=True)
        result = self._run()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn(PLAN_A_TITLE, result.stdout)
        self.assertNotIn("Ambiguous plan", result.stdout)

    def test_nested_slug_plan_without_pointer_still_competes(self) -> None:
        # Competing = .active_plan OR at least one <slug>/task_plan.md.
        self.build_tree(nested=True)
        (self.project / ".planning" / ".active_plan").unlink()
        result = self._run()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("Ambiguous plan", result.stdout)
        self.assertNotIn(PLAN_A_TITLE, result.stdout)

    # -- 8. PLANNING_DISABLED still silences everything --------------------
    def test_planning_disabled_beats_broken_pin(self) -> None:
        self.build_tree(nested=True)
        result = self._run(
            {
                "PLANNING_DISABLED": "1",
                "PWF_PLAN_ROOT": str(self.workspace / "does-not-exist"),
            }
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stdout.strip())


class CodexAdapterPlanRootPinTests(NestedTreeMixin):
    """The Python adapter route: per-tool-call hooks fail closed SILENTLY."""

    def run_python_hook(
        self, script_name: str, payload: dict, env_extra: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        for var in SCRUB_VARS:
            env.pop(var, None)
        if env_extra:
            env.update(env_extra)
        return subprocess.run(
            [sys.executable, str(HOOKS_DIR / script_name)],
            input=json.dumps(payload),
            text=True,
            encoding="utf-8",
            capture_output=True,
            cwd=str(self.workspace),
            env=env,
            check=False,
        )

    def test_effective_plan_root_unit_semantics(self) -> None:
        sys.path.insert(0, str(HOOKS_DIR))
        try:
            import codex_hook_adapter as adapter

            self.build_tree(nested=True)
            for var in SCRUB_VARS:
                os.environ.pop(var, None)
            try:
                # Unset: cwd passes through untouched (legacy invariant).
                self.assertEqual(
                    self.workspace, adapter.effective_plan_root(self.workspace)
                )
                # Valid pin: the pinned root wins.
                os.environ["PWF_PLAN_ROOT"] = str(self.project)
                self.assertEqual(
                    self.project.resolve(),
                    adapter.effective_plan_root(self.workspace),
                )
                # Broken pin: fail closed.
                os.environ["PWF_PLAN_ROOT"] = str(self.workspace / "missing")
                self.assertIsNone(adapter.effective_plan_root(self.workspace))
            finally:
                os.environ.pop("PWF_PLAN_ROOT", None)
        finally:
            sys.path.pop(0)

    def test_only_verified_darwin_system_aliases_are_trusted(self) -> None:
        sys.path.insert(0, str(HOOKS_DIR))
        try:
            import codex_hook_adapter as adapter

            alias_info = SimpleNamespace(st_mode=stat.S_IFLNK)
            directory_info = SimpleNamespace(st_mode=stat.S_IFDIR)
            mappings = {
                "/var": ("private/var", "/private/var"),
                "/tmp": ("private/tmp", "/private/tmp"),
                "/etc": ("private/etc", "/private/etc"),
            }
            for alias, (link_text, target) in mappings.items():
                with self.subTest(alias=alias):
                    with (
                        mock.patch.object(adapter.sys, "platform", "darwin"),
                        mock.patch.object(adapter.os.path, "abspath", return_value=alias),
                        mock.patch.object(adapter.os, "readlink", return_value=link_text),
                        mock.patch.object(adapter.os.path, "realpath", return_value=target),
                        mock.patch.object(
                            adapter.Path,
                            "lstat",
                            side_effect=[alias_info, directory_info, directory_info],
                        ),
                    ):
                        self.assertTrue(
                            adapter._is_trusted_darwin_system_alias(Path(alias))
                        )

            with self.subTest(case="wrong-target"):
                with (
                    mock.patch.object(adapter.sys, "platform", "darwin"),
                    mock.patch.object(adapter.os.path, "abspath", return_value="/var"),
                    mock.patch.object(adapter.os, "readlink", return_value="private/evil"),
                    mock.patch.object(adapter.os.path, "realpath", return_value="/private/var"),
                    mock.patch.object(
                        adapter.Path,
                        "lstat",
                        side_effect=[alias_info],
                    ),
                ):
                    self.assertFalse(
                        adapter._is_trusted_darwin_system_alias(Path("/var"))
                    )

            with self.subTest(case="unlisted-alias"):
                with mock.patch.object(adapter.sys, "platform", "darwin"):
                    self.assertFalse(
                        adapter._is_trusted_darwin_system_alias(Path("/usr/local"))
                    )
        finally:
            sys.path.pop(0)

    def test_relative_and_sibling_plan_root_pins_fail_closed(self) -> None:
        sys.path.insert(0, str(HOOKS_DIR))
        try:
            import codex_hook_adapter as adapter

            self.build_tree(nested=True)
            sibling = self.tmp / "sibling"
            sibling.mkdir()
            try:
                os.environ["PWF_PLAN_ROOT"] = "project"
                self.assertIsNone(adapter.effective_plan_root(self.workspace))
                os.environ["PWF_PLAN_ROOT"] = str(sibling)
                self.assertIsNone(adapter.effective_plan_root(self.workspace))
            finally:
                os.environ.pop("PWF_PLAN_ROOT", None)
        finally:
            sys.path.pop(0)

    def test_run_sh_valid_pin_uses_nested_effective_root(self) -> None:
        self.build_tree(nested=True)
        # run_sh requires the shell script name as argv[1], so exercise it
        # directly here rather than through run_python_hook's fixed argv.
        env = os.environ.copy()
        for var in SCRUB_VARS:
            env.pop(var, None)
        env["PWF_PLAN_ROOT"] = str(self.project)
        result = subprocess.run(
            [sys.executable, str(HOOKS_DIR / "run_sh.py"), "user-prompt-submit.sh"],
            input=json.dumps({"cwd": str(self.workspace), "session_id": "sess-x"}),
            text=True,
            encoding="utf-8",
            capture_output=True,
            cwd=self.workspace,
            env=env,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        if os.name == "nt" and not result.stdout.strip():
            self.skipTest("Git for Windows sh.exe not resolvable on this runner")
        payload = json.loads(result.stdout)
        context = payload["hookSpecificOutput"]["additionalContext"]
        self.assertIn(PLAN_B_TITLE, context)
        self.assertNotIn(PLAN_A_TITLE, context)

    def test_pre_tool_use_broken_pin_is_silent(self) -> None:
        self.build_tree(nested=True)
        result = self.run_python_hook(
            "pre_tool_use.py",
            {"cwd": str(self.workspace), "tool_input": {"command": "pwd"}},
            {"PWF_PLAN_ROOT": str(self.workspace / "does-not-exist")},
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stdout.strip(), "per-tool-call hooks refuse silently")

    def test_post_tool_use_broken_pin_is_silent(self) -> None:
        self.build_tree(nested=True)
        result = self.run_python_hook(
            "post_tool_use.py",
            {"cwd": str(self.workspace), "tool_response": "ok"},
            {"PWF_PLAN_ROOT": str(self.workspace / "does-not-exist")},
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stdout.strip())

    def test_stop_broken_pin_is_silent(self) -> None:
        self.build_tree(nested=True, phased_nested=True)
        result = self.run_python_hook(
            "stop.py",
            {"cwd": str(self.workspace), "stop_hook_active": False},
            {"PWF_PLAN_ROOT": str(self.workspace / "does-not-exist")},
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stdout.strip())

    def test_permission_request_broken_pin_is_silent(self) -> None:
        self.build_tree(nested=True)
        result = self.run_python_hook(
            "permission_request.py",
            {"cwd": str(self.workspace), "tool_name": "Bash"},
            {"PWF_PLAN_ROOT": str(self.workspace / "does-not-exist")},
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stdout.strip())

    def test_pre_tool_use_valid_pin_injects_nested_context(self) -> None:
        self.build_tree(nested=True)
        result = self.run_python_hook(
            "pre_tool_use.py",
            {"cwd": str(self.workspace), "tool_input": {"command": "pwd"}},
            {"PWF_PLAN_ROOT": str(self.project)},
        )
        self.assertEqual(0, result.returncode, result.stderr)
        if os.name == "nt" and not result.stdout.strip():
            self.skipTest("Git for Windows sh.exe not resolvable on this runner")
        payload = json.loads(result.stdout)
        context = payload["hookSpecificOutput"]["additionalContext"]
        self.assertIn(PLAN_B_TITLE, context, "pinned root's plan must reach the model")
        self.assertNotIn(PLAN_A_TITLE, context, "parent plan must not leak through")

    def test_stop_valid_pin_reports_nested_plan_phases(self) -> None:
        self.build_tree(nested=True, phased_nested=True)
        result = self.run_python_hook(
            "stop.py",
            {"cwd": str(self.workspace), "stop_hook_active": False},
            {"PWF_PLAN_ROOT": str(self.project)},
        )
        self.assertEqual(0, result.returncode, result.stderr)
        if os.name == "nt" and not result.stdout.strip():
            self.skipTest("Git for Windows sh.exe not resolvable on this runner")
        payload = json.loads(result.stdout)
        self.assertIn("Task in progress", payload["systemMessage"])

    def test_permission_request_valid_pin_emits_reminder(self) -> None:
        self.build_tree(nested=True)
        result = self.run_python_hook(
            "permission_request.py",
            {"cwd": str(self.workspace), "tool_name": "Bash"},
            {"PWF_PLAN_ROOT": str(self.project)},
        )
        self.assertEqual(0, result.returncode, result.stderr)
        if os.name == "nt" and not result.stdout.strip():
            self.skipTest("Git for Windows sh.exe not resolvable on this runner")
        payload = json.loads(result.stdout)
        self.assertIn("Active plan", payload["systemMessage"])

    def test_pinned_sessions_guard_reads_the_pinned_root(self) -> None:
        # Session isolation armed at the PIN, not at the cwd: an unattached
        # session must refuse even though the cwd has no sessions dir.
        self.build_tree(nested=True)
        (self.project / ".planning" / "sessions").mkdir()
        result = self.run_python_hook(
            "pre_tool_use.py",
            {"cwd": str(self.workspace), "session_id": "sess-x", "tool_input": {}},
            {"PWF_PLAN_ROOT": str(self.project)},
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stdout.strip())

    def test_unpinned_adapter_behavior_unchanged(self) -> None:
        # Legacy invariant at the adapter layer: no pin, cwd resolution.
        self.build_tree(nested=False)
        result = self.run_python_hook(
            "pre_tool_use.py",
            {"cwd": str(self.workspace), "tool_input": {"command": "pwd"}},
        )
        self.assertEqual(0, result.returncode, result.stderr)
        if os.name == "nt" and not result.stdout.strip():
            self.skipTest("Git for Windows sh.exe not resolvable on this runner")
        payload = json.loads(result.stdout)
        self.assertIn(PLAN_A_TITLE, payload["hookSpecificOutput"]["additionalContext"])


if __name__ == "__main__":
    unittest.main()
