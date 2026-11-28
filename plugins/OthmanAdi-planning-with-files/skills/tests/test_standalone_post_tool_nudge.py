"""Standalone skill hooks deliver context and isolate their turn throttle.

Claude Code passes hook identity in JSON on stdin.  It does not export the
session id for shell commands, and plain stdout is context only for a small
set of events.  The standalone skill therefore needs one entrypoint that owns
stdin parsing, forwards the real session id to plan resolution, and emits the
event-specific response shape.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = REPO_ROOT / "skills" / "planning-with-files"
HOOK = SKILL_DIR / "scripts" / "skill-hook.sh"
INJECT = SKILL_DIR / "scripts" / "inject-plan.sh"
NUDGE = "Update progress.md with what you just did"


def have_sh() -> bool:
    return shutil.which("sh") is not None


@unittest.skipUnless(have_sh(), "requires a POSIX sh")
class StandaloneSkillHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory(prefix="pwf-standalone-hook-")
        self.root = Path(self.tempdir.name)
        (self.root / "task_plan.md").write_text(
            '# Standalone plan "quoted" \\ marker\n### Phase 1\n- [ ] work\n',
            encoding="utf-8",
        )
        (self.root / "progress.md").write_text("# Progress\n", encoding="utf-8")
        self.cache = self.root / "_cache"
        self.cache.mkdir()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _env(self, **extra: str) -> dict[str, str]:
        env = os.environ.copy()
        for key in (
            "PLAN_ID",
            "PWF_PLAN_ROOT",
            "PLANNING_DISABLED",
            "PWF_SESSION_ID",
            "PWF_SESSION_KEY",
        ):
            env.pop(key, None)
        env["XDG_CACHE_HOME"] = str(self.cache)
        env["PYTHON_BIN"] = sys.executable
        env.update(extra)
        return env

    @staticmethod
    def _payload(event: str, session: str | None = "alpha", **extra: object) -> str:
        data: dict[str, object] = {"hook_event_name": event, "cwd": "ignored-by-hook"}
        if session is not None:
            data["session_id"] = session
        data.update(extra)
        return json.dumps(data)

    def _run(
        self,
        event: str,
        *,
        payload: str | None = None,
        cwd: Path | None = None,
        **extra_env: str,
    ) -> subprocess.CompletedProcess[str]:
        event_names = {
            "userprompt": "UserPromptSubmit",
            "pretool": "PreToolUse",
            "posttool": "PostToolUse",
            "precompact": "PreCompact",
            "stop": "Stop",
        }
        return subprocess.run(
            ["sh", str(HOOK), f"--event={event}"],
            cwd=str(cwd or self.root),
            env=self._env(**extra_env),
            input=payload if payload is not None else self._payload(event_names[event]),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=180,
            check=False,
        )

    def _probe_python(self) -> tuple[Path, Path]:
        marker = self.root / "python-probed"
        probe = self.root / "not-python.sh"
        probe.write_text(
            f'#!/bin/sh\nprintf "%s\\n" probed >> "{marker.as_posix()}"\nexit 1\n',
            encoding="utf-8",
        )
        probe.chmod(0o700)
        return probe, marker

    def test_posttool_emits_model_context_as_valid_json(self) -> None:
        result = self._run("posttool")

        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertNotIn("systemMessage", payload)
        block = payload["hookSpecificOutput"]
        self.assertEqual("PostToolUse", block["hookEventName"])
        self.assertIn(NUDGE, block["additionalContext"])

    def test_pretool_serializes_injector_output_as_model_context(self) -> None:
        result = self._run("pretool")

        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        block = payload["hookSpecificOutput"]
        self.assertEqual("PreToolUse", block["hookEventName"])
        self.assertIn("Standalone plan", block["additionalContext"])
        self.assertIn('"quoted" \\ marker', block["additionalContext"])

    def test_userprompt_preserves_injector_stdout_and_rearms_the_turn(self) -> None:
        first = self._run("posttool")
        second = self._run("posttool")
        prompt = self._run("userprompt")
        after_prompt = self._run("posttool")

        self.assertIn(NUDGE, first.stdout)
        self.assertEqual("", second.stdout)
        self.assertIn("Standalone plan", prompt.stdout)
        self.assertIn(NUDGE, after_prompt.stdout)

    def test_real_stdin_sessions_do_not_silence_each_other(self) -> None:
        alpha_first = self._run("posttool", PWF_SESSION_ID="forged-env")
        alpha_second = self._run("posttool", PWF_SESSION_ID="another-forged-env")
        beta_first = self._run(
            "posttool",
            payload=self._payload("PostToolUse", "beta"),
            PWF_SESSION_ID="alpha",
        )

        self.assertIn(NUDGE, alpha_first.stdout)
        self.assertEqual("", alpha_second.stdout)
        self.assertIn(NUDGE, beta_first.stdout)

    def test_prompt_and_agent_identity_make_subagent_throttles_independent(self) -> None:
        worker_a = self._payload(
            "PostToolUse", "alpha", prompt_id="prompt-1", agent_id="worker-a"
        )
        worker_b = self._payload(
            "PostToolUse", "alpha", prompt_id="prompt-1", agent_id="worker-b"
        )
        worker_a_next_turn = self._payload(
            "PostToolUse", "alpha", prompt_id="prompt-2", agent_id="worker-a"
        )

        self.assertIn(NUDGE, self._run("posttool", payload=worker_a).stdout)
        self.assertEqual("", self._run("posttool", payload=worker_a).stdout)
        self.assertIn(NUDGE, self._run("posttool", payload=worker_b).stdout)
        self.assertEqual("", self._run("posttool", payload=worker_b).stdout)
        self.assertIn(NUDGE, self._run("posttool", payload=worker_a_next_turn).stdout)

    def test_nested_session_id_text_cannot_replace_host_identity(self) -> None:
        payload = self._payload(
            "PostToolUse",
            "alpha",
            tool_input={"command": 'printf \'{"session_id":"beta"}\''},
        )

        self.assertIn(NUDGE, self._run("posttool", payload=payload).stdout)
        self.assertEqual("", self._run("posttool", payload=payload).stdout)
        self.assertIn(
            NUDGE,
            self._run(
                "posttool", payload=self._payload("PostToolUse", "beta")
            ).stdout,
        )

    def test_missing_or_malformed_identity_never_uses_a_shared_empty_slot(self) -> None:
        missing = self._payload("PostToolUse", None)

        self.assertIn(NUDGE, self._run("posttool", payload=missing).stdout)
        self.assertIn(NUDGE, self._run("posttool", payload=missing).stdout)
        self.assertIn(NUDGE, self._run("posttool", payload="not json").stdout)
        self.assertIn(NUDGE, self._run("posttool", payload="not json").stdout)

    def test_broken_cache_fails_toward_the_reminder(self) -> None:
        broken = self.root / "cache-is-a-file"
        broken.write_text("not a directory", encoding="utf-8")

        first = self._run("posttool", XDG_CACHE_HOME=str(broken))
        second = self._run("posttool", XDG_CACHE_HOME=str(broken))

        self.assertIn(NUDGE, first.stdout)
        self.assertIn(NUDGE, second.stdout)

    def test_symlinked_cache_root_fails_toward_the_reminder(self) -> None:
        xdg = self.root / "symlink-xdg"
        target = self.root / "cache-target"
        xdg.mkdir()
        target.mkdir()
        try:
            (xdg / "pwf-turn").symlink_to(target, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"directory symlinks unavailable: {exc}")

        first = self._run("posttool", XDG_CACHE_HOME=str(xdg))
        second = self._run("posttool", XDG_CACHE_HOME=str(xdg))

        self.assertIn(NUDGE, first.stdout)
        self.assertIn(NUDGE, second.stdout)
        self.assertEqual([], list(target.iterdir()), "unsafe cache target was modified")

    @unittest.skipIf(os.name == "nt", "POSIX ownership and mode contract")
    def test_cache_root_permissions_are_tightened_before_use(self) -> None:
        xdg = self.root / "mode-xdg"
        cache_root = xdg / "pwf-turn"
        cache_root.mkdir(parents=True)
        cache_root.chmod(0o777)

        first = self._run("posttool", XDG_CACHE_HOME=str(xdg))
        second = self._run("posttool", XDG_CACHE_HOME=str(xdg))

        self.assertIn(NUDGE, first.stdout)
        self.assertEqual("", second.stdout)
        self.assertEqual(0o700, cache_root.stat().st_mode & 0o777)

    def test_disabled_and_rejected_selectors_stay_silent(self) -> None:
        disabled = self._run("posttool", PLANNING_DISABLED="1")
        invalid = self._run("posttool", PLAN_ID="missing-plan")

        self.assertEqual("", disabled.stdout)
        self.assertEqual("", invalid.stdout)

    def test_disabled_or_missing_plan_does_not_probe_an_interpreter(self) -> None:
        probe, marker = self._probe_python()

        disabled = self._run(
            "posttool", PLANNING_DISABLED="1", PWF_TRUSTED_PYTHON=str(probe)
        )
        (self.root / "task_plan.md").unlink()
        missing = self._run("posttool", PWF_TRUSTED_PYTHON=str(probe))

        self.assertEqual("", disabled.stdout)
        self.assertEqual("", missing.stdout)
        self.assertFalse(marker.exists(), "rejected hooks must not execute an interpreter")

    def test_escaping_selected_plan_does_not_probe_a_path_interpreter(self) -> None:
        probe, marker = self._probe_python()
        probe_dir = self.root / "probe-bin"
        probe_dir.mkdir()
        probe = probe.replace(probe_dir / "python3")
        (self.root / "task_plan.md").unlink()
        outside = Path(tempfile.mkdtemp(prefix="pwf-hook-outside-"))
        self.addCleanup(shutil.rmtree, outside, True)
        (outside / "task_plan.md").write_text("# outside canary\n", encoding="utf-8")
        planning = self.root / ".planning"
        planning.mkdir()
        try:
            (planning / "escape").symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"directory symlinks unavailable: {exc}")

        escaped = self._run(
            "posttool",
            PLAN_ID="escape",
            PWF_TRUSTED_PYTHON="",
            PYTHON_BIN="",
            PATH=f"{probe_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        )

        self.assertEqual("", escaped.stdout)
        self.assertFalse(
            marker.exists(), "containment refusal must precede PATH interpreter probing"
        )

    def test_invalid_explicit_python_never_falls_through_to_path_for_identity(self) -> None:
        probe, marker = self._probe_python()

        first = self._run("posttool", PWF_TRUSTED_PYTHON=str(probe))
        second = self._run("posttool", PWF_TRUSTED_PYTHON=str(probe))

        self.assertTrue(marker.exists(), "the explicit candidate was not checked")
        self.assertIn(NUDGE, first.stdout)
        self.assertIn(
            NUDGE,
            second.stdout,
            "falling through to PATH would parse identity and suppress this reminder",
        )

    def test_host_identity_controls_armed_session_admission(self) -> None:
        (self.root / "task_plan.md").unlink()
        plan = self.root / ".planning" / "plan-a"
        plan.mkdir(parents=True)
        (plan / "task_plan.md").write_text("# attached alpha marker\n", encoding="utf-8")
        sessions = self.root / ".planning" / "sessions"
        sessions.mkdir()
        (sessions / "alpha.attached").write_text("", encoding="utf-8")

        alpha = self._run("pretool", PLAN_ID="plan-a", PWF_SESSION_ID="beta")
        beta = self._run(
            "pretool",
            payload=self._payload("PreToolUse", "beta"),
            PLAN_ID="plan-a",
            PWF_SESSION_ID="alpha",
        )
        alpha_post = self._run("posttool", PLAN_ID="plan-a", PWF_SESSION_ID="beta")
        beta_post = self._run(
            "posttool",
            payload=self._payload("PostToolUse", "beta"),
            PLAN_ID="plan-a",
            PWF_SESSION_ID="alpha",
        )
        alpha_compact = self._run(
            "precompact", PLAN_ID="plan-a", PWF_SESSION_ID="beta"
        )
        beta_compact = self._run(
            "precompact",
            payload=self._payload("PreCompact", "beta"),
            PLAN_ID="plan-a",
            PWF_SESSION_ID="alpha",
        )

        self.assertIn("attached alpha marker", alpha.stdout)
        self.assertEqual("", beta.stdout)
        self.assertIn(NUDGE, alpha_post.stdout)
        self.assertEqual("", beta_post.stdout)
        self.assertIn("ensure progress.md", alpha_compact.stdout)
        self.assertEqual("", beta_compact.stdout)

    def test_armed_unpinned_multi_plan_selection_is_silent_until_pinned(self) -> None:
        (self.root / "task_plan.md").unlink()
        planning = self.root / ".planning"
        for slug in ("plan-a", "plan-b"):
            plan = planning / slug
            plan.mkdir(parents=True)
            (plan / "task_plan.md").write_text(f"# {slug}\n", encoding="utf-8")
        (planning / ".active_plan").write_text("plan-a\n", encoding="utf-8")
        sessions = planning / "sessions"
        sessions.mkdir()
        (sessions / "alpha.attached").write_text("", encoding="utf-8")

        ambiguous = self._run("posttool")
        pinned = self._run("posttool", PLAN_ID="plan-a")

        self.assertEqual("", ambiguous.stdout)
        self.assertIn(NUDGE, pinned.stdout)

    def test_stop_preserves_native_payload_for_recursive_stop_guard(self) -> None:
        (self.root / ".mode").write_text("autonomous gate\n", encoding="utf-8")
        (self.root / "task_plan.md").write_text(
            "# Gated plan\n### Phase 1: Work\n- **Status:** in_progress\n",
            encoding="utf-8",
        )
        (self.root / "ledger-main.jsonl").write_text(
            '{"tick":1,"event":"progress"}\n', encoding="utf-8"
        )

        blocking = self._run(
            "stop",
            payload=self._payload("Stop", "alpha", stop_hook_active=False),
        )
        recursive = self._run(
            "stop",
            payload=self._payload("Stop", "alpha", stop_hook_active=True),
        )

        self.assertIn('"decision":"block"', blocking.stdout)
        self.assertNotIn('"decision":"block"', recursive.stdout)


if __name__ == "__main__":
    unittest.main()
