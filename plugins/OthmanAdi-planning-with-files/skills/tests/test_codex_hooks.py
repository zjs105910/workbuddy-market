import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
CODEX_ROOT = REPO_ROOT / ".codex"
HOOKS_JSON = CODEX_ROOT / "hooks.json"
HOOKS_DIR = CODEX_ROOT / "hooks"


class CodexHooksTests(unittest.TestCase):
    def run_python_hook(self, script_name: str, payload: dict, cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(HOOKS_DIR / script_name)],
            input=json.dumps(payload),
            text=True,
            encoding="utf-8",
            capture_output=True,
            cwd=str(cwd),
            check=False,
        )

    def run_shell_hook(self, script_name: str, cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess[str]:
        shell_env = (env or os.environ).copy()
        shell = shutil.which("sh", path=shell_env.get("PATH"))
        if os.name == "nt":
            sys.path.insert(0, str(HOOKS_DIR))
            try:
                import codex_hook_adapter as adapter

                shell, extra_path_dirs = adapter._windows_git_bash()
            finally:
                sys.path.pop(0)
            if shell is None:
                raise unittest.SkipTest("Git for Windows sh.exe is unavailable")
            if extra_path_dirs:
                shell_env["PATH"] = os.pathsep.join(
                    [*extra_path_dirs, shell_env.get("PATH", "")]
                )
            shell_env.setdefault("PYTHON_BIN", sys.executable)
        elif shell is None:
            raise unittest.SkipTest("POSIX sh is unavailable")
        return subprocess.run(
            [shell, str(HOOKS_DIR / script_name)],
            text=True,
            encoding="utf-8",
            capture_output=True,
            cwd=str(cwd),
            env=shell_env,
            check=False,
        )

    def run_shell_front_door(
        self,
        sh_script: str,
        payload: dict,
        cwd: Path,
        env: dict | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(HOOKS_DIR / "run_sh.py"), sh_script],
            input=json.dumps(payload),
            text=True,
            encoding="utf-8",
            capture_output=True,
            cwd=str(cwd),
            env=env,
            check=False,
        )

    def test_hooks_json_declares_all_expected_codex_events(self) -> None:
        self.assertTrue(HOOKS_JSON.exists(), ".codex/hooks.json is missing")

        payload = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
        self.assertEqual(
            {
                "SessionStart",
                "UserPromptSubmit",
                "PreToolUse",
                "PermissionRequest",
                "PostToolUse",
                "PreCompact",
                "Stop",
            },
            set(payload["hooks"]),
        )
        self.assertEqual(
            "startup|resume|clear|compact",
            payload["hooks"]["SessionStart"][0]["matcher"],
        )

    def test_permission_request_adapter_emits_plan_reminder(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            root.joinpath("task_plan.md").write_text(
                "# Task Plan\n### Phase 1\n- **Status:** in_progress\n",
                encoding="utf-8",
            )

            result = self.run_python_hook(
                "permission_request.py",
                {"cwd": str(root), "tool_name": "Bash"},
                root,
            )

        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertIn("systemMessage", payload)
        self.assertIn("Active plan", payload["systemMessage"])

    def test_permission_request_silent_without_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            result = self.run_python_hook(
                "permission_request.py",
                {"cwd": str(root), "tool_name": "Bash"},
                root,
            )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stdout.strip())

    def test_permission_request_resolves_scoped_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_dir = root / ".planning" / "task-a"
            plan_dir.mkdir(parents=True)
            plan_dir.joinpath("task_plan.md").write_text("# Scoped Plan\n", encoding="utf-8")
            root.joinpath(".planning", ".active_plan").write_text("task-a\n", encoding="utf-8")

            result = self.run_python_hook(
                "permission_request.py",
                {"cwd": str(root), "tool_name": "Bash"},
                root,
            )

        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertIn("Active plan", payload["systemMessage"])

    def test_session_start_reuses_plan_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as home:
            root = Path(tmpdir)
            root.joinpath("task_plan.md").write_text(
                "# Task Plan\n\n## Goal\nShip Codex hooks\n",
                encoding="utf-8",
            )
            root.joinpath("progress.md").write_text(
                "# Progress\n\nFinished adapter draft.\n",
                encoding="utf-8",
            )
            root.joinpath("findings.md").write_text(
                "# Findings\n\n- reuse cursor hooks\n",
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["HOME"] = home
            result = self.run_shell_hook("session-start.sh", root, env=env)

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("ACTIVE PLAN", result.stdout)
        self.assertIn("Ship Codex hooks", result.stdout)
        self.assertIn("Finished adapter draft", result.stdout)

    def test_session_start_catchup_is_explicitly_no_history(self) -> None:
        text = HOOKS_DIR.joinpath("session-start.sh").read_text(encoding="utf-8")
        self.assertIn('session-catchup.py" --no-history', text)
        self.assertNotIn('session-catchup.py" --metadata', text)
        self.assertNotIn('session-catchup.py" --replay', text)

    def test_pre_tool_use_adapter_emits_additional_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            root.joinpath("task_plan.md").write_text(
                textwrap.dedent(
                    """\
                    # Task Plan
                    ### Phase 1: Discovery
                    - **Status:** complete
                    """
                ),
                encoding="utf-8",
            )

            result = self.run_python_hook(
                "pre_tool_use.py",
                {"cwd": str(root), "tool_input": {"command": "pwd"}},
                root,
            )

        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        hook_output = payload["hookSpecificOutput"]
        self.assertEqual("PreToolUse", hook_output["hookEventName"])
        self.assertIn("# Task Plan", hook_output["additionalContext"])

    def test_pre_tool_use_adapter_preserves_unicode_as_ascii_safe_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            root.joinpath("task_plan.md").write_text("# \u4efb\u52a1\u8ba1\u5212\n", encoding="utf-8")

            result = self.run_python_hook(
                "pre_tool_use.py",
                {"cwd": str(root), "tool_input": {"command": "pwd"}},
                root,
            )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(result.stdout.isascii())
        payload = json.loads(result.stdout)
        self.assertIn("\u4efb\u52a1\u8ba1\u5212", payload["hookSpecificOutput"]["additionalContext"])

    def test_post_tool_use_adapter_emits_progress_reminder(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            root.joinpath("task_plan.md").write_text("# Task Plan\n", encoding="utf-8")

            result = self.run_python_hook(
                "post_tool_use.py",
                {"cwd": str(root), "tool_response": "ok"},
                root,
            )

        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        # The nudge is addressed to Claude, so it goes into the model context
        # as additionalContext (#239). systemMessage is documented as a warning
        # shown to the USER, so the model never received this instruction.
        self.assertNotIn("systemMessage", payload)
        block = payload["hookSpecificOutput"]
        self.assertEqual("PostToolUse", block["hookEventName"])
        self.assertIn("progress.md", block["additionalContext"])

    def test_pre_compact_emits_flush_reminder(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            root.joinpath("task_plan.md").write_text("# Task Plan\n", encoding="utf-8")
            root.joinpath(".plan-attestation").write_text("abc123\n", encoding="utf-8")

            result = self.run_shell_hook("pre-compact.sh", root)

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("[planning-with-files] PreCompact", result.stdout)
        self.assertIn("progress.md", result.stdout)
        self.assertIn("Plan-SHA256", result.stdout)

    def test_pre_compact_silent_without_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            result = self.run_shell_hook("pre-compact.sh", root)

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stdout.strip())

    def test_stop_adapter_reports_incomplete_plan_without_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            root.joinpath("task_plan.md").write_text(
                textwrap.dedent(
                    """\
                    ### Phase 1: Discovery
                    - **Status:** complete

                    ### Phase 2: Implementation
                    - **Status:** pending
                    """
                ),
                encoding="utf-8",
            )

            first = self.run_python_hook(
                "stop.py",
                {"cwd": str(root), "stop_hook_active": False},
                root,
            )
            second = self.run_python_hook(
                "stop.py",
                {"cwd": str(root), "stop_hook_active": True},
                root,
            )

        self.assertEqual(0, first.returncode, first.stderr)
        self.assertEqual(0, second.returncode, second.stderr)

        first_payload = json.loads(first.stdout)
        second_payload = json.loads(second.stdout)

        self.assertNotIn("decision", first_payload)
        self.assertNotIn("reason", first_payload)
        self.assertIn("Task in progress", first_payload["systemMessage"])
        self.assertIn("progress.md is up to date", first_payload["systemMessage"])
        self.assertNotIn("continue working", first_payload["systemMessage"])
        self.assertIn("Task in progress", second_payload["systemMessage"])

    def test_every_hook_has_windows_override_without_posix_isms(self) -> None:
        """issue #201: on Windows Codex runs commandWindows, not the POSIX command.

        Every hook must carry a commandWindows routed through pwf-hook.cmd, and it
        must contain none of the tokens that break under the Windows interpreter
        (python3 alias stub, /dev/null, $HOME, the missing `true` command). Runs on
        every OS so unix CI also enforces the JSON stays valid and the keys stay.
        """
        payload = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
        for event, entries in payload["hooks"].items():
            for entry in entries:
                for hook in entry["hooks"]:
                    cw = hook.get("commandWindows", "")
                    self.assertTrue(cw, f"{event} hook is missing commandWindows")
                    self.assertIn("pwf-hook.cmd", cw, f"{event} commandWindows not routed through the launcher")
                    for bad in ("$HOME", "2>/dev/null", "|| true", "python3 "):
                        self.assertNotIn(bad, cw, f"{event} commandWindows still contains POSIX-ism {bad!r}")

    def test_posix_shell_events_route_through_run_sh_adapter(self) -> None:
        payload = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
        scripts = {
            "SessionStart": "session-start.sh",
            "UserPromptSubmit": "user-prompt-submit.sh",
            "PreCompact": "pre-compact.sh",
        }

        for event, script in scripts.items():
            command = payload["hooks"][event][0]["hooks"][0]["command"]
            self.assertEqual(
                f'python3 .codex/hooks/run_sh.py {script} 2>/dev/null || '
                f'python3 "$HOME/.codex/hooks/run_sh.py" {script} 2>/dev/null || true',
                command,
            )

    def test_adapter_uses_explicit_utf8_for_shell_output(self) -> None:
        sys.path.insert(0, str(HOOKS_DIR))
        try:
            import codex_hook_adapter as adapter

            completed = subprocess.CompletedProcess(["sh"], 0, "ok\n", "")
            with mock.patch.object(adapter, "_windows_git_bash", return_value=("sh", [])), mock.patch.object(
                adapter.subprocess, "run", return_value=completed
            ) as run:
                stdout, stderr = adapter.run_shell_script("user-prompt-submit.sh", Path.cwd())
        finally:
            sys.path.pop(0)

        self.assertEqual("ok", stdout)
        self.assertEqual("", stderr)
        self.assertEqual("utf-8", run.call_args.kwargs["encoding"])
        self.assertEqual("replace", run.call_args.kwargs["errors"])

    def test_emit_json_is_ascii_safe_and_round_trips_unicode(self) -> None:
        sys.path.insert(0, str(HOOKS_DIR))
        try:
            import codex_hook_adapter as adapter

            buffer = io.BytesIO()
            stream = io.TextIOWrapper(buffer, encoding="ascii")
            with mock.patch.object(adapter.sys, "stdout", stream):
                adapter.emit_json({"message": "\u4e2d\u6587"})
                stream.flush()
            raw = buffer.getvalue().decode("ascii")
            stream.detach()
        finally:
            sys.path.pop(0)

        self.assertTrue(raw.isascii())
        self.assertEqual("\u4e2d\u6587", json.loads(raw)["message"])

    def test_run_sh_front_door_serializes_shell_events(self) -> None:
        """The shared POSIX and Windows path emits event-appropriate Codex JSON."""
        if os.name == "nt":
            sys.path.insert(0, str(HOOKS_DIR))
            try:
                import codex_hook_adapter as adapter
                sh_path, _ = adapter._windows_git_bash()
            finally:
                sys.path.pop(0)
            if sh_path is None:
                self.skipTest("Git for Windows sh.exe not resolvable on this runner")
        elif shutil.which("sh") is None:
            self.skipTest("POSIX sh is unavailable")

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            root.joinpath("task_plan.md").write_text(
                "# \u4efb\u52a1\u8ba1\u5212\n\n## Goal\nWindows hook parity\n", encoding="utf-8"
            )
            root.joinpath("progress.md").write_text("# Progress\n", encoding="utf-8")

            user_prompt = self.run_shell_front_door("user-prompt-submit.sh", {"cwd": str(root)}, root)
            session_start = self.run_shell_front_door("session-start.sh", {"cwd": str(root)}, root)
            pre_compact = self.run_shell_front_door("pre-compact.sh", {"cwd": str(root)}, root)

        for result in (user_prompt, session_start, pre_compact):
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue(result.stdout.isascii())

        user_payload = json.loads(user_prompt.stdout)
        self.assertEqual("UserPromptSubmit", user_payload["hookSpecificOutput"]["hookEventName"])
        self.assertIn("Windows hook parity", user_payload["hookSpecificOutput"]["additionalContext"])
        self.assertIn("\u4efb\u52a1\u8ba1\u5212", user_payload["hookSpecificOutput"]["additionalContext"])

        session_payload = json.loads(session_start.stdout)
        self.assertEqual("SessionStart", session_payload["hookSpecificOutput"]["hookEventName"])
        self.assertIn("Windows hook parity", session_payload["hookSpecificOutput"]["additionalContext"])

        compact_payload = json.loads(pre_compact.stdout)
        self.assertTrue(compact_payload["continue"])
        self.assertIn("PreCompact", compact_payload["systemMessage"])

    def test_run_sh_front_door_is_silent_without_context_or_when_disabled(self) -> None:
        if os.name == "nt":
            sys.path.insert(0, str(HOOKS_DIR))
            try:
                import codex_hook_adapter as adapter
                sh_path, _ = adapter._windows_git_bash()
            finally:
                sys.path.pop(0)
            if sh_path is None:
                self.skipTest("Git for Windows sh.exe not resolvable on this runner")
        elif shutil.which("sh") is None:
            self.skipTest("POSIX sh is unavailable")

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            no_context = [
                self.run_shell_front_door(script, {"cwd": str(root)}, root)
                for script in ("session-start.sh", "user-prompt-submit.sh", "pre-compact.sh")
            ]

            root.joinpath("task_plan.md").write_text("# Task Plan\n", encoding="utf-8")
            disabled_env = os.environ.copy()
            disabled_env["PLANNING_DISABLED"] = "1"
            disabled = [
                self.run_shell_front_door(script, {"cwd": str(root)}, root, env=disabled_env)
                for script in ("session-start.sh", "user-prompt-submit.sh", "pre-compact.sh")
            ]

        for result in (*no_context, *disabled):
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("", result.stdout.strip())

    @unittest.skipUnless(
        os.name == "nt",
        "Windows-shaped path; System32 comparison only meaningful on Windows",
    )
    def test_windows_git_bash_rejects_wsl_launcher_in_system32(self) -> None:
        """A bare `bash` on PATH resolving into System32 is the WSL launcher.

        _windows_git_bash must never hand that path back to callers even when
        it is the only `bash` shutil.which can see; it should keep looking
        (and return a real Git-for-Windows sh.exe, or None) instead.
        """
        sys.path.insert(0, str(HOOKS_DIR))
        try:
            import codex_hook_adapter as adapter

            def fake_which(exe, *args, **kwargs):
                if exe == "sh":
                    return None
                if exe == "bash":
                    return r"C:\windows\system32\bash.EXE"
                return None

            with mock.patch.object(adapter.shutil, "which", side_effect=fake_which):
                sh_path, _ = adapter._windows_git_bash()
        finally:
            sys.path.pop(0)

        if sh_path is not None:
            self.assertNotIn("system32", sh_path.lower())

    @unittest.skipUnless(
        os.name == "nt",
        "Windows-shaped path; WindowsApps comparison only meaningful on Windows",
    )
    def test_windows_git_bash_rejects_wsl_launcher_in_windowsapps(self) -> None:
        """The Microsoft Store WSL alias lives under WindowsApps, not System32.

        Even a working WSL bash there cannot execute C:\\ script paths, so
        _windows_git_bash must reject it the same way it rejects System32.
        """
        sys.path.insert(0, str(HOOKS_DIR))
        try:
            import codex_hook_adapter as adapter

            def fake_which(exe, *args, **kwargs):
                if exe == "sh":
                    return None
                if exe == "bash":
                    return r"C:\Users\x\AppData\Local\Microsoft\WindowsApps\bash.exe"
                return None

            with mock.patch.object(adapter.shutil, "which", side_effect=fake_which):
                sh_path, _ = adapter._windows_git_bash()
        finally:
            sys.path.pop(0)

        if sh_path is not None:
            self.assertNotIn("windowsapps", sh_path.lower())


if __name__ == "__main__":
    unittest.main()
