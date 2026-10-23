"""Tests for Codex session isolation — addresses #146.

Goal: a Codex session must not receive another session's plan context just because
task_plan.md exists in cwd. Each session must explicitly attach. Attach state
lives at .planning/sessions/<session_id>.attached and is opt-in.

Backward compat: if no .planning/sessions/ directory exists at all, hooks fall
back to legacy "any session in this cwd sees the plan" behavior to avoid breaking
existing single-session users on upgrade.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import hashlib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
HOOKS_DIR = REPO_ROOT / ".codex" / "hooks"


def session_key(root: Path, session_id: str) -> str:
    digest = hashlib.sha256()
    project = os.path.normcase(os.path.realpath(os.path.abspath(root))).replace("\\", "/")
    for value in ("codex", project, session_id):
        encoded = value.encode("utf-8", errors="surrogatepass")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


class CodexSessionIsolationTests(unittest.TestCase):
    def run_python_hook(
        self,
        script_name: str,
        payload: dict,
        cwd: Path,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(HOOKS_DIR / script_name)],
            input=json.dumps(payload),
            text=True,
            encoding="utf-8",
            capture_output=True,
            cwd=str(cwd),
            check=False,
        )

    def write_plan(self, root: Path) -> None:
        (root / "task_plan.md").write_text(
            "# Task Plan\n\n## Goal\nShip Codex isolation\n\n### Phase 1: Discovery\n- **Status:** in_progress\n",
            encoding="utf-8",
        )
        (root / "progress.md").write_text("# Progress\n\nstarted\n", encoding="utf-8")
        (root / "findings.md").write_text("# Findings\n", encoding="utf-8")

    def attach_session(self, root: Path, session_id: str) -> None:
        sessions_dir = root / ".planning" / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        (sessions_dir / f"{session_key(root, session_id)}.attached").write_text("attached\n", encoding="utf-8")

    def attach_safe_legacy_session(self, root: Path, session_id: str) -> None:
        sessions_dir = root / ".planning" / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        (sessions_dir / f"{session_id}.attached").write_text("attached\n", encoding="utf-8")

    def shell_env(self, session_id: str) -> dict[str, str]:
        trusted_python = str(Path(sys.executable).resolve())
        if os.name == "nt":
            trusted_python = trusted_python.replace("/", "\\")
        return {
            **os.environ,
            "PWF_SESSION_ID": session_id,
            "PWF_TRUSTED_PYTHON": trusted_python,
        }

    # ------------------------------------------------------------------
    # Backward compat: no .planning/sessions/ => legacy single-session mode
    # ------------------------------------------------------------------

    def test_legacy_mode_user_prompt_submit_injects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_plan(root)
            payload = {"cwd": str(root), "session_id": "sess-A"}
            result = subprocess.run(
                ["sh", str(HOOKS_DIR / "user-prompt-submit.sh")],
                cwd=str(root),
                text=True,
                encoding="utf-8",
                capture_output=True,
                env=self.shell_env("sess-A"),
                check=False,
            )
            self.assertIn("ACTIVE PLAN", result.stdout)

    # ------------------------------------------------------------------
    # Isolation: when sessions/ dir exists, only attached sessions see context
    # ------------------------------------------------------------------

    def test_user_prompt_submit_silent_for_unattached_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_plan(root)
            self.attach_session(root, "sess-A")
            # Session B is NOT attached
            env = self.shell_env("sess-B")
            result = subprocess.run(
                ["sh", str(HOOKS_DIR / "user-prompt-submit.sh")],
                cwd=str(root),
                text=True,
                encoding="utf-8",
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertNotIn("ACTIVE PLAN", result.stdout)

    def test_user_prompt_submit_injects_for_attached_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_plan(root)
            self.attach_session(root, "sess-A")
            env = self.shell_env("sess-A")
            result = subprocess.run(
                ["sh", str(HOOKS_DIR / "user-prompt-submit.sh")],
                cwd=str(root),
                text=True,
                encoding="utf-8",
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertIn("ACTIVE PLAN", result.stdout)
            self.assertIn("Ship Codex isolation", result.stdout)

    def test_documented_safe_raw_session_sentinel_still_injects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_plan(root)
            self.attach_safe_legacy_session(root, "sess-A")
            result = subprocess.run(
                ["sh", str(HOOKS_DIR / "user-prompt-submit.sh")],
                cwd=root,
                text=True,
                encoding="utf-8",
                capture_output=True,
                env=self.shell_env("sess-A"),
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("ACTIVE PLAN", result.stdout)
            self.assertIn("Ship Codex isolation", result.stdout)

    def test_pre_tool_use_silent_for_unattached_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_plan(root)
            self.attach_session(root, "sess-A")
            payload = {"cwd": str(root), "session_id": "sess-B"}
            result = self.run_python_hook("pre_tool_use.py", payload, root)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("", result.stdout.strip())

    def test_unattested_autonomous_plan_is_blocked_on_user_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_plan(root)
            (root / ".mode").write_text("autonomous\n", encoding="ascii")
            result = subprocess.run(
                ["sh", str(HOOKS_DIR / "user-prompt-submit.sh")],
                cwd=root,
                text=True,
                encoding="utf-8",
                capture_output=True,
                env=self.shell_env("sess-A"),
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertNotIn("Ship Codex isolation", result.stdout)
            self.assertIn("v3 mode requires attested plan", result.stdout)

    def test_attested_autonomous_and_gated_pre_tool_never_recite_plan(self) -> None:
        for marker in ("autonomous", "autonomous gate"):
            with self.subTest(marker=marker), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.write_plan(root)
                plan = root / "task_plan.md"
                (root / ".mode").write_text(marker + "\n", encoding="ascii")
                (root / ".plan-attestation").write_text(
                    hashlib.sha256(plan.read_bytes()).hexdigest() + "\n",
                    encoding="ascii",
                )
                result = self.run_python_hook(
                    "pre_tool_use.py",
                    {"cwd": str(root), "session_id": "sess-A", "tool_input": {}},
                    root,
                )
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual("", result.stdout.strip())
                self.assertNotIn("Ship Codex isolation", result.stderr)

    def test_planning_disabled_does_not_execute_supplied_interpreter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_plan(root)
            marker = root / "fake-python-executed"
            fake = root / "fake-python"
            fake.write_text(f"#!/bin/sh\nprintf touched > '{marker.as_posix()}'\n", encoding="utf-8")
            fake.chmod(0o755)
            env = {
                **self.shell_env("sess-A"),
                "PLANNING_DISABLED": "1",
                "PWF_TRUSTED_PYTHON": str(fake),
            }
            result = subprocess.run(
                ["sh", str(HOOKS_DIR / "user-prompt-submit.sh")],
                cwd=root,
                text=True,
                encoding="utf-8",
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("", result.stdout.strip())
            self.assertFalse(marker.exists())

    def test_no_plan_does_not_execute_supplied_interpreter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = root / "fake-python-executed"
            fake = root / "fake-python"
            fake.write_text(f"#!/bin/sh\nprintf touched > '{marker.as_posix()}'\n", encoding="utf-8")
            fake.chmod(0o755)
            env = {
                **self.shell_env("sess-A"),
                "PWF_TRUSTED_PYTHON": str(fake),
            }
            result = subprocess.run(
                ["sh", str(HOOKS_DIR / "user-prompt-submit.sh")],
                cwd=root,
                text=True,
                encoding="utf-8",
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("", result.stdout.strip())
            self.assertFalse(marker.exists())

    def test_windows_drive_relative_and_unc_interpreters_are_rejected(self) -> None:
        if os.name != "nt":
            self.skipTest("Windows path classification")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_plan(root)
            for candidate in (r"C:python.exe", r"\\server\share\python.exe", "//server/share/python"):
                with self.subTest(candidate=candidate):
                    env = {
                        **self.shell_env("sess-A"),
                        "PWF_TRUSTED_PYTHON": candidate,
                    }
                    result = subprocess.run(
                        ["sh", str(HOOKS_DIR / "user-prompt-submit.sh")],
                        cwd=root,
                        text=True,
                        encoding="utf-8",
                        capture_output=True,
                        env=env,
                        check=False,
                    )
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertEqual("", result.stdout.strip())

    def test_stop_does_not_block_unattached_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_plan(root)
            self.attach_session(root, "sess-A")
            payload = {"cwd": str(root), "session_id": "sess-B", "stop_hook_active": False}
            result = self.run_python_hook("stop.py", payload, root)
            self.assertEqual(0, result.returncode, result.stderr)
            stdout = result.stdout.strip()
            if stdout:
                emitted = json.loads(stdout)
                self.assertNotEqual(emitted.get("decision"), "block")

    def test_two_sessions_same_cwd_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_plan(root)
            self.attach_session(root, "sess-A")
            # A sees plan, B silent — single repro for cross-session leak
            env_a = self.shell_env("sess-A")
            env_b = self.shell_env("sess-B")
            stale_key = "a" * 64
            env_a["PWF_SESSION_KEY"] = stale_key
            env_b["PWF_SESSION_KEY"] = stale_key
            ra = subprocess.run(
                ["sh", str(HOOKS_DIR / "user-prompt-submit.sh")],
                cwd=str(root), text=True, encoding="utf-8", capture_output=True, env=env_a, check=False,
            )
            rb = subprocess.run(
                ["sh", str(HOOKS_DIR / "user-prompt-submit.sh")],
                cwd=str(root), text=True, encoding="utf-8", capture_output=True, env=env_b, check=False,
            )
            self.assertIn("ACTIVE PLAN", ra.stdout)
            self.assertNotIn("ACTIVE PLAN", rb.stdout)

    def test_linked_plan_directory_never_counts_toward_binding(self) -> None:
        # #270: a symlinked or junctioned plan directory is not selectable, so
        # the Codex counter skips it like the shell counters and Hermes do.
        sys.path.insert(0, str(HOOKS_DIR))
        try:
            import codex_hook_adapter as adapter
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                real = root / ".planning" / "2026-09-19-real"
                real.mkdir(parents=True)
                (real / "task_plan.md").write_text("# REAL\n", encoding="utf-8")
                target = root / "linked-target"
                target.mkdir()
                (target / "task_plan.md").write_text("# LINKED\n", encoding="utf-8")
                link = root / ".planning" / "2026-09-19-linked"
                if os.name == "nt":
                    made = subprocess.run(["cmd", "/d", "/c", "mklink", "/J", str(link), str(target)],
                                          capture_output=True, text=True, check=False)
                    if made.returncode != 0:
                        self.skipTest("junction creation unavailable: " + made.stderr.strip())
                else:
                    try:
                        link.symlink_to(target, target_is_directory=True)
                    except OSError as exc:
                        self.skipTest(f"symlink creation unavailable: {exc}")
                self.assertTrue((link / "task_plan.md").is_file(), "the link must resolve for the test to mean anything")
                self.assertFalse(adapter.session_plan_requires_binding(root))
                other = root / ".planning" / "2026-09-19-other"
                other.mkdir()
                (other / "task_plan.md").write_text("# OTHER\n", encoding="utf-8")
                self.assertTrue(adapter.session_plan_requires_binding(root))
        finally:
            sys.path.pop(0)

    def test_hostile_native_session_ids_are_opaque_fixed_width_keys(self) -> None:
        sys.path.insert(0, str(HOOKS_DIR))
        try:
            import codex_hook_adapter as adapter
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                sessions = root / ".planning" / "sessions"
                sessions.mkdir(parents=True)
                hostile = (
                    "../escape",
                    "a/b",
                    r"C:\\absolute",
                    r"\\server\share",
                    "unicode∕slash",
                    "control\nline",
                    "control\x00null",
                )
                for session_id in hostile:
                    key = adapter.state_key("codex", root, session_id)
                    self.assertIsNotNone(key)
                    assert key is not None
                    self.assertRegex(key, r"^[0-9a-f]{64}$")
                    sentinel = sessions / f"{key}.attached"
                    sentinel.write_text("attached\n", encoding="utf-8")
                    self.assertTrue(adapter.is_session_attached(root, session_id))
                self.assertEqual(len(hostile), len(list(sessions.glob("*.attached"))))
                self.assertFalse((root / "escape.attached").exists())
        finally:
            sys.path.pop(0)

    def test_native_payload_session_id_overrides_ambient_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_plan(root)
            self.attach_session(root, "native-session")
            env = self.shell_env("ambient-wrong-session")
            result = subprocess.run(
                [sys.executable, str(HOOKS_DIR / "run_sh.py"), "user-prompt-submit.sh"],
                input=json.dumps({"cwd": str(root), "session_id": "native-session"}),
                text=True,
                encoding="utf-8",
                capture_output=True,
                cwd=root,
                env=env,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            payload = json.loads(result.stdout)
            self.assertIn("Ship Codex isolation", payload["hookSpecificOutput"]["additionalContext"])

    def test_symlink_attachment_sentinel_is_refused_when_supported(self) -> None:
        sys.path.insert(0, str(HOOKS_DIR))
        try:
            import codex_hook_adapter as adapter
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                sessions = root / ".planning" / "sessions"
                sessions.mkdir(parents=True)
                target = root / "target"
                target.write_text("attached\n", encoding="utf-8")
                key = adapter.state_key("codex", root, "linked")
                assert key is not None
                try:
                    (sessions / f"{key}.attached").symlink_to(target)
                except OSError:
                    self.skipTest("symlink creation is unavailable on this host")
                self.assertFalse(adapter.is_session_attached(root, "linked"))
        finally:
            sys.path.pop(0)

    def test_safe_raw_symlink_attachment_is_refused_when_supported(self) -> None:
        sys.path.insert(0, str(HOOKS_DIR))
        try:
            import codex_hook_adapter as adapter
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                sessions = root / ".planning" / "sessions"
                sessions.mkdir(parents=True)
                target = root / "target"
                target.write_text("attached\n", encoding="utf-8")
                try:
                    (sessions / "sess-A.attached").symlink_to(target)
                except OSError:
                    self.skipTest("symlink creation is unavailable on this host")
                self.assertFalse(adapter.is_session_attached(root, "sess-A"))
        finally:
            sys.path.pop(0)


if __name__ == "__main__":
    unittest.main()
