"""Cursor adapter manifests and command output follow the current hook schema."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CURSOR_ROOT = REPO_ROOT / ".cursor"
HOOKS = CURSOR_ROOT / "hooks"
UNSUPPORTED_EVENTS = {"userPromptSubmit"}


def shell_python_is_usable() -> bool:
    """True when python3 or python runs from sh, as session-start.sh needs."""
    sh = shutil.which("sh")
    if not sh:
        return False
    probe = (
        'for PY in "$(command -v python3)" "$(command -v python)"; do '
        '[ -n "$PY" ] && "$PY" -I -c "import json" && exit 0; done; exit 1'
    )
    result = subprocess.run(
        [sh, "-c", probe], capture_output=True, text=True, timeout=30, check=False
    )
    return result.returncode == 0


class CursorHookSchemaTests(unittest.TestCase):
    def test_manifests_only_use_supported_prompt_and_permission_events(self) -> None:
        for manifest_name in ("hooks.json", "hooks.windows.json"):
            with self.subTest(manifest=manifest_name):
                manifest = json.loads((CURSOR_ROOT / manifest_name).read_text())
                hooks = manifest["hooks"]
                self.assertTrue(UNSUPPORTED_EVENTS.isdisjoint(hooks))
                self.assertIn("sessionStart", hooks)
                self.assertIn("preToolUse", hooks)
                self.assertIn("postToolUse", hooks)
                self.assertIn("session-start", hooks["sessionStart"][0]["command"])
                if manifest_name == "hooks.windows.json":
                    for entries in hooks.values():
                        for entry in entries:
                            self.assertIn("-NoProfile", entry["command"])

    @unittest.skipUnless(shutil.which("sh"), "requires POSIX sh")
    def test_shell_session_start_emits_plan_as_additional_context(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pwf-cursor-schema-") as tmp:
            root = Path(tmp)
            (root / "task_plan.md").write_text("# SESSION-START-PLAN\n", encoding="utf-8")
            (root / "progress.md").write_text("Recent progress\n", encoding="utf-8")
            env = os.environ.copy()
            env.pop("PLANNING_DISABLED", None)

            result = subprocess.run(
                ["sh", str(HOOKS / "session-start.sh")],
                cwd=root,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            payload = json.loads(result.stdout)
            self.assertIn("SESSION-START-PLAN", payload["additional_context"])

    @unittest.skipUnless(shutil.which("sh"), "requires POSIX sh")
    def test_shell_session_start_returns_valid_json_when_python_fails(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pwf-cursor-schema-") as tmp:
            root = Path(tmp)
            (root / "task_plan.md").write_text("# SESSION-START-PLAN\n", encoding="utf-8")
            bin_dir = root / "bin"
            bin_dir.mkdir()
            # The hook falls back from python3 to python, so both must fail.
            for name in ("python3", "python"):
                python_stub = bin_dir / name
                python_stub.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8", newline="\n")
                python_stub.chmod(0o755)
            env = os.environ.copy()
            env.pop("PLANNING_DISABLED", None)
            env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")

            result = subprocess.run(
                ["sh", str(HOOKS / "session-start.sh")],
                cwd=root,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual({}, json.loads(result.stdout))

    @unittest.skipUnless(shutil.which("sh"), "requires POSIX sh")
    def test_shell_permission_and_post_tool_hooks_emit_schema_fields(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pwf-cursor-schema-") as tmp:
            root = Path(tmp)
            (root / "task_plan.md").write_text("# Active plan\n", encoding="utf-8")
            env = os.environ.copy()
            env.pop("PLANNING_DISABLED", None)

            pre_tool = subprocess.run(
                ["sh", str(HOOKS / "pre-tool-use.sh")],
                cwd=root,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            post_tool = subprocess.run(
                ["sh", str(HOOKS / "post-tool-use.sh")],
                cwd=root,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(0, pre_tool.returncode, pre_tool.stderr)
            self.assertEqual({"permission": "allow"}, json.loads(pre_tool.stdout))
            self.assertEqual(0, post_tool.returncode, post_tool.stderr)
            self.assertIn(
                "additional_context", json.loads(post_tool.stdout)
            )

    def test_shell_session_start_runs_python_isolated(self) -> None:
        # Hook interpreters run with -I (v3.17.0), so a json.py planted in the
        # project directory is never imported by the hook.
        text = (HOOKS / "session-start.sh").read_text(encoding="utf-8")
        invocations = [line for line in text.splitlines() if '"$PYTHON"' in line]
        self.assertTrue(invocations, "no Python invocation found in session-start.sh")
        for line in invocations:
            self.assertIn('"$PYTHON" -I -X utf8 ', line)

    @unittest.skipUnless(shell_python_is_usable(), "shell Python is not usable")
    def test_shell_session_start_ignores_project_json_module(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pwf-cursor-schema-") as tmp:
            root = Path(tmp)
            (root / "task_plan.md").write_text("# ISOLATED-PLAN\n", encoding="utf-8")
            (root / "json.py").write_text(
                "open('PLANTED_json', 'w').close()\nraise RuntimeError('shadow loaded')\n",
                encoding="utf-8",
            )
            env = os.environ.copy()
            env.pop("PLANNING_DISABLED", None)

            result = subprocess.run(
                ["sh", str(HOOKS / "session-start.sh")],
                cwd=root,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertFalse(
                (root / "PLANTED_json").exists(),
                "session-start.sh imported the project json.py",
            )
            self.assertIn(
                "ISOLATED-PLAN", json.loads(result.stdout)["additional_context"]
            )


COMPLETE_PLAN = (
    "# Plan\n### Phase 1: Build\n**Status:** complete\n"
    "### Phase 2: Verify\n**Status:** complete\n"
)
INCOMPLETE_PLAN = (
    "# Plan\n### Phase 1: Build\n**Status:** complete\n"
    "### Phase 2: Verify\n**Status:** in_progress\n"
)


class CursorStopHookTests(unittest.TestCase):
    """Cursor submits a stop hook's followup_message as the next user message.

    A finished plan must therefore produce no output at all, or every stop in a
    project with a completed plan triggers automatic follow-up turns (up to the
    manifest's loop_limit). An incomplete plan still asks Cursor to continue.
    """

    def stop_commands(self) -> list[tuple[str, list[str]]]:
        commands = []
        if shutil.which("sh"):
            commands.append(("sh", ["sh", str(HOOKS / "stop.sh")]))
        for name in ("powershell.exe", "pwsh"):
            executable = shutil.which(name)
            if executable:
                commands.append((name, [
                    executable, "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-File", str(HOOKS / "stop.ps1"),
                ]))
        if not commands:
            self.skipTest("neither POSIX sh nor PowerShell is available")
        return commands

    def run_stop(self, command: list[str], plan: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory(prefix="pwf-cursor-stop-") as tmp:
            root = Path(tmp)
            (root / "task_plan.md").write_text(plan, encoding="utf-8")
            env = os.environ.copy()
            for name in ("PLANNING_DISABLED", "PLAN_ID", "PWF_PLAN_ROOT"):
                env.pop(name, None)
            return subprocess.run(
                command,
                cwd=root,
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=60,
                check=False,
            )

    def test_stop_is_silent_when_every_phase_is_complete(self) -> None:
        for name, command in self.stop_commands():
            with self.subTest(shell=name):
                result = self.run_stop(command, COMPLETE_PLAN)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual("", result.stdout.strip().lstrip("﻿"))

    def test_stop_still_continues_an_incomplete_plan(self) -> None:
        for name, command in self.stop_commands():
            with self.subTest(shell=name):
                result = self.run_stop(command, INCOMPLETE_PLAN)
                self.assertEqual(0, result.returncode, result.stderr)
                payload = json.loads(result.stdout.strip().lstrip("﻿"))
                self.assertIn(
                    "Task incomplete (1/2 phases done)", payload["followup_message"]
                )


if __name__ == "__main__":
    unittest.main()
