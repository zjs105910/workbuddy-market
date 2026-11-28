"""Integration tests: Codex hooks use resolve-plan-dir.sh to find the active plan.

These tests confirm that after the #148 fix, all four Codex hook shell scripts
correctly locate task_plan.md through the resolver rather than assuming the
legacy root path. They complement the unit tests in test_resolve_plan_dir.py
by exercising the full hook→resolver→plan-file chain.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
HOOKS_DIR = REPO_ROOT / ".codex" / "hooks"


def shell_and_env() -> tuple[str, dict[str, str]]:
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


def run_hook(script: str, cwd: Path, env_extra: dict | None = None) -> subprocess.CompletedProcess[str]:
    shell, env = shell_and_env()
    env.pop("PLAN_ID", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [shell, str(HOOKS_DIR / script)],
        cwd=str(cwd),
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=env,
        check=False,
    )


def write_plan_in_dir(plan_dir: Path, goal: str = "Ship the feature") -> None:
    plan_dir.mkdir(parents=True, exist_ok=True)
    (plan_dir / "task_plan.md").write_text(
        f"# Task Plan\n\n## Goal\n{goal}\n\n### Phase 1: Work\n- **Status:** in_progress\n",
        encoding="utf-8",
    )
    (plan_dir / "progress.md").write_text("# Progress\n\nstarted\n", encoding="utf-8")
    (plan_dir / "findings.md").write_text("# Findings\n", encoding="utf-8")


class HookResolverIntegrationTests(unittest.TestCase):

    @unittest.skipIf(os.name == "nt", "POSIX PATH poisoning contract")
    def test_security_sensitive_hooks_do_not_execute_path_python(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_dir = root / ".planning" / "safe-plan"
            write_plan_in_dir(plan_dir, goal="Trusted plan goal")
            (root / ".planning" / ".active_plan").write_text(
                "safe-plan\n", encoding="utf-8"
            )
            marker = root / "path-python-executed"
            fake_bin = root / "fake-bin"
            fake_bin.mkdir()
            for name in ("python3", "python"):
                fake_python = fake_bin / name
                fake_python.write_text(
                    f"#!/bin/sh\nprintf touched > '{marker.as_posix()}'\nexit 1\n",
                    encoding="utf-8",
                )
                fake_python.chmod(0o755)
            # Force canonicalize() past both ordinary command fallbacks. The
            # resolver must fail closed without consulting PATH for Python.
            for name in ("realpath", "readlink"):
                fake_tool = fake_bin / name
                fake_tool.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
                fake_tool.chmod(0o755)

            shell, env = shell_and_env()
            for name in ("PWF_TRUSTED_PYTHON", "PYTHON_BIN", "PLAN_ID"):
                env.pop(name, None)
            env.pop("PWF_PLAN_ROOT", None)
            env["PATH"] = os.pathsep.join((str(fake_bin), env.get("PATH", "")))

            for script in ("user-prompt-submit.sh", "pre-tool-use.sh"):
                with self.subTest(script=script):
                    result = subprocess.run(
                        [shell, str(HOOKS_DIR / script)],
                        cwd=root,
                        text=True,
                        encoding="utf-8",
                        capture_output=True,
                        env=env,
                        check=False,
                    )
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertNotIn("Trusted plan goal", result.stdout + result.stderr)
                    self.assertFalse(marker.exists())

    def test_resolver_uses_explicit_legacy_python_when_path_tools_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_dir = root / ".planning" / "safe-plan"
            write_plan_in_dir(plan_dir)
            (root / ".planning" / ".active_plan").write_text(
                "safe-plan\n", encoding="utf-8"
            )
            fake_bin = root / "fake-bin"
            fake_bin.mkdir()
            for name in ("realpath", "readlink"):
                fake_tool = fake_bin / name
                fake_tool.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
                fake_tool.chmod(0o755)

            shell, env = shell_and_env()
            env.pop("PWF_TRUSTED_PYTHON", None)
            env["PYTHON_BIN"] = str(Path(sys.executable).resolve())
            env["PATH"] = os.pathsep.join((str(fake_bin), env.get("PATH", "")))

            result = subprocess.run(
                [shell, str(HOOKS_DIR / "resolve-plan-dir.sh")],
                cwd=root,
                text=True,
                encoding="utf-8",
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            resolved = result.stdout.strip().replace("\\", "/")
            self.assertTrue(
                resolved.endswith("/.planning/safe-plan"),
                f"unexpected resolved path: {result.stdout!r}",
            )

    @unittest.skipIf(os.name == "nt", "POSIX rejection harness")
    def test_resolver_rejects_unsafe_explicit_python_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_dir = root / ".planning" / "safe-plan"
            write_plan_in_dir(plan_dir)
            (root / ".planning" / ".active_plan").write_text(
                "safe-plan\n", encoding="utf-8"
            )
            marker = root / "unsafe-python-executed"
            fake_bin = root / "fake-bin"
            fake_bin.mkdir()
            for name in ("realpath", "readlink"):
                fake_tool = fake_bin / name
                fake_tool.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
                fake_tool.chmod(0o755)

            for candidate in (
                root / "relative-python",
                root / "C:drive-relative-python",
                root / "WindowsApps" / "python3",
            ):
                candidate.parent.mkdir(parents=True, exist_ok=True)
                candidate.write_text(
                    f"#!/bin/sh\nprintf touched > '{marker.as_posix()}'\nexit 1\n",
                    encoding="utf-8",
                )
                candidate.chmod(0o755)

            shell = shutil.which("sh")
            if shell is None:
                self.skipTest("POSIX sh is unavailable")
            base_env = os.environ.copy()
            base_env.pop("PYTHON_BIN", None)
            base_env["PATH"] = os.pathsep.join(
                (str(fake_bin), base_env.get("PATH", ""))
            )
            supplied = (
                "./relative-python",
                "C:drive-relative-python",
                str(root / "WindowsApps" / "python3"),
                "//server/share/python3",
                r"\\server\share\python3.exe",
            )
            for candidate in supplied:
                with self.subTest(candidate=candidate):
                    marker.unlink(missing_ok=True)
                    env = {**base_env, "PWF_TRUSTED_PYTHON": candidate}
                    result = subprocess.run(
                        [shell, str(HOOKS_DIR / "resolve-plan-dir.sh")],
                        cwd=root,
                        text=True,
                        encoding="utf-8",
                        capture_output=True,
                        env=env,
                        check=False,
                    )
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertEqual("", result.stdout)
                    self.assertFalse(marker.exists())

    @unittest.skipIf(os.name == "nt", "POSIX PATH poisoning contract")
    def test_resolver_mtime_fallback_does_not_execute_path_python(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_plan_in_dir(root / ".planning" / "safe-plan")
            marker = root / "path-python-executed"
            fake_bin = root / "fake-bin"
            fake_bin.mkdir()
            for name in ("python3", "python"):
                fake_python = fake_bin / name
                fake_python.write_text(
                    f"#!/bin/sh\nprintf touched > '{marker.as_posix()}'\nexit 1\n",
                    encoding="utf-8",
                )
                fake_python.chmod(0o755)
            for name in ("stat", "date"):
                fake_tool = fake_bin / name
                fake_tool.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
                fake_tool.chmod(0o755)

            shell = shutil.which("sh")
            if shell is None:
                self.skipTest("POSIX sh is unavailable")
            env = os.environ.copy()
            for name in ("PWF_TRUSTED_PYTHON", "PYTHON_BIN", "PLAN_ID"):
                env.pop(name, None)
            env["PATH"] = os.pathsep.join((str(fake_bin), env.get("PATH", "")))

            result = subprocess.run(
                [shell, str(HOOKS_DIR / "resolve-plan-dir.sh")],
                cwd=root,
                text=True,
                encoding="utf-8",
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("", result.stdout)
            self.assertFalse(marker.exists())

    def test_global_resolver_is_a_thin_canonical_forwarder(self) -> None:
        resolver = (HOOKS_DIR / "resolve-plan-dir.sh").read_text(encoding="utf-8")
        self.assertIn("../skills/planning-with-files/scripts/resolve-plan-dir.sh", resolver)
        self.assertIn('exec sh "${CANONICAL_RESOLVER}" "$@"', resolver)
        self.assertNotIn("resolve_latest_dir()", resolver)

    # ------------------------------------------------------------------
    # user-prompt-submit.sh
    # ------------------------------------------------------------------

    def test_user_prompt_submit_silent_with_no_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = run_hook("user-prompt-submit.sh", Path(tmp))
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertNotIn("ACTIVE PLAN", result.stdout)

    def test_user_prompt_submit_injects_from_planning_subdir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_dir = root / ".planning" / "2026-01-10-backend-refactor"
            write_plan_in_dir(plan_dir, goal="Refactor the auth layer")
            (root / ".planning" / ".active_plan").write_text(
                "2026-01-10-backend-refactor\n", encoding="utf-8"
            )
            result = run_hook("user-prompt-submit.sh", root)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("ACTIVE PLAN", result.stdout)
            self.assertIn("Refactor the auth layer", result.stdout)

    def test_user_prompt_submit_legacy_root_still_works(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "task_plan.md").write_text(
                "# Task Plan\n\n## Goal\nLegacy goal\n\n### Phase 1: Work\n- **Status:** in_progress\n",
                encoding="utf-8",
            )
            (root / "progress.md").write_text("# Progress\n", encoding="utf-8")
            result = run_hook("user-prompt-submit.sh", root)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("ACTIVE PLAN", result.stdout)
            self.assertIn("Legacy goal", result.stdout)

    def test_user_prompt_submit_env_plan_id_pins_correct_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_plan_in_dir(root / ".planning" / "task-a", goal="Task A goal")
            write_plan_in_dir(root / ".planning" / "task-b", goal="Task B goal")
            (root / ".planning" / ".active_plan").write_text("task-b\n", encoding="utf-8")
            # Override with env var to force task-a
            result = run_hook("user-prompt-submit.sh", root, env_extra={"PLAN_ID": "task-a"})
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("Task A goal", result.stdout)
            self.assertNotIn("Task B goal", result.stdout)

    def test_utf8_bom_active_pointer_cannot_bypass_multiple_plan_refusal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            safe = root / ".planning" / "safe"
            write_plan_in_dir(safe, goal="BOM-safe goal")
            decoy = root / ".planning" / "newer-decoy"
            write_plan_in_dir(decoy, goal="Newest fallback goal")
            # Neither pointer parsing nor newest fallback may select a task
            # while another named plan competes with it.
            os.utime(safe, (100, 100))
            os.utime(decoy, (200, 200))
            (root / ".planning" / ".active_plan").write_bytes(b"\xef\xbb\xbfsafe\n")

            result = run_hook("user-prompt-submit.sh", root)

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("Set PLAN_ID=<slug>", result.stdout)
            self.assertNotIn("BOM-safe goal", result.stdout)
            self.assertNotIn("Newest fallback goal", result.stdout)

            # The same BOM pointer remains usable in a single-plan project.
            (decoy / "task_plan.md").unlink()
            single = run_hook("user-prompt-submit.sh", root)
            self.assertIn("BOM-safe goal", single.stdout)

    def test_user_prompt_submit_rejects_traversal_plan_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_plan_in_dir(root / ".planning" / "safe", goal="Workspace plan")
            write_plan_in_dir(root / "outside", goal="Escaped plan")
            (root / ".planning" / ".active_plan").write_text("safe\n", encoding="utf-8")

            result = run_hook(
                "user-prompt-submit.sh",
                root,
                env_extra={"PLAN_ID": "../outside"},
            )

            self.assertEqual(0, result.returncode, result.stderr)
            # Never the escaped plan: that was always the point of this test.
            self.assertNotIn("Escaped plan", result.stdout)
            # And since issue #237, not the workspace plan either. Refusing to
            # leave .planning was right; handing back a plan the operator did
            # not name is the same wrong-plan harm as a typo, so a rejected
            # selector now stops resolution and says so.
            self.assertNotIn("Workspace plan", result.stdout)
            self.assertIn("PLAN_ID does not name a plan directory", result.stdout)

    def test_user_prompt_submit_rejects_external_symlink_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside_tmp:
            root = Path(tmp)
            safe = root / ".planning" / "safe"
            outside = Path(outside_tmp) / "outside"
            write_plan_in_dir(safe, goal="Workspace plan")
            write_plan_in_dir(outside, goal="Escaped plan")
            (root / ".planning" / ".active_plan").write_text("safe\n", encoding="utf-8")
            escape = root / ".planning" / "escape"
            try:
                try:
                    escape.symlink_to(outside, target_is_directory=True)
                except OSError as symlink_error:
                    if os.name != "nt":
                        self.skipTest(f"directory symlinks are unavailable: {symlink_error}")
                    junction = subprocess.run(
                        ["cmd", "/d", "/c", "mklink", "/J", str(escape), str(outside)],
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        capture_output=True,
                        check=False,
                    )
                    if junction.returncode != 0:
                        self.skipTest("directory symlinks and junctions are unavailable")

                result = run_hook(
                    "user-prompt-submit.sh",
                    root,
                    env_extra={"PLAN_ID": "escape"},
                )

                self.assertEqual(0, result.returncode, result.stderr)
                # The containment refusal is unchanged and remains the point.
                self.assertNotIn("Escaped plan", result.stdout)
                # Since issue #237 a rejected selector no longer substitutes
                # the pointer's plan; a failed containment check is a rejection
                # like any other.
                self.assertNotIn("Workspace plan", result.stdout)
            finally:
                if escape.is_symlink():
                    escape.unlink()
                elif os.name == "nt" and escape.exists():
                    # os.rmdir removes the junction itself, never its target.
                    os.rmdir(escape)

    # ------------------------------------------------------------------
    # pre-tool-use.sh
    # ------------------------------------------------------------------

    def test_pre_tool_use_allows_with_no_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = run_hook("pre-tool-use.sh", Path(tmp))
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("allow", result.stdout)

    def test_pre_tool_use_surfaces_plan_from_subdir_on_stderr(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_dir = root / ".planning" / "2026-01-10-my-task"
            write_plan_in_dir(plan_dir, goal="My task goal")
            (root / ".planning" / ".active_plan").write_text(
                "2026-01-10-my-task\n", encoding="utf-8"
            )
            result = run_hook("pre-tool-use.sh", root)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("allow", result.stdout)
            self.assertIn("My task goal", result.stderr)

    # ------------------------------------------------------------------
    # stop.sh
    # ------------------------------------------------------------------

    def test_stop_silent_with_no_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = run_hook("stop.sh", Path(tmp))
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("", result.stdout.strip())

    def test_stop_reports_incomplete_from_subdir_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_dir = root / ".planning" / "2026-01-10-feature"
            write_plan_in_dir(plan_dir, goal="Build feature")
            (root / ".planning" / ".active_plan").write_text(
                "2026-01-10-feature\n", encoding="utf-8"
            )
            result = run_hook("stop.sh", root)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("followup_message", result.stdout)

    # ------------------------------------------------------------------
    # post-tool-use.sh
    # ------------------------------------------------------------------

    def test_post_tool_use_silent_with_no_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = run_hook("post-tool-use.sh", Path(tmp))
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("", result.stdout.strip())

    def test_post_tool_use_reminds_when_plan_in_subdir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_dir = root / ".planning" / "2026-01-10-work"
            write_plan_in_dir(plan_dir)
            (root / ".planning" / ".active_plan").write_text(
                "2026-01-10-work\n", encoding="utf-8"
            )
            result = run_hook("post-tool-use.sh", root)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("progress.md", result.stdout)


if __name__ == "__main__":
    unittest.main()
