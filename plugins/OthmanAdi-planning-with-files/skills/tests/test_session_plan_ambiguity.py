"""Real-process regression canaries for same-root session plan ambiguity."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
HOOKS = REPO_ROOT / ".codex" / "hooks"
INJECT_PLAN = REPO_ROOT / "skills" / "planning-with-files" / "scripts" / "inject-plan.sh"
NOTICE = "Set PLAN_ID=<slug>"
VALIDATION_TOKEN = "PWF_PLAN_ACCEPTED_V1"
PREFLIGHT_TOKEN = "PWF_PLAN_ELIGIBLE_V1"


def session_key(root: Path, session_id: str) -> str:
    digest = hashlib.sha256()
    project = os.path.normcase(os.path.realpath(os.path.abspath(root))).replace("\\", "/")
    for value in ("codex", project, session_id):
        encoded = value.encode("utf-8", errors="surrogatepass")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


@unittest.skipUnless(shutil.which("sh"), "sh is required")
class SessionPlanAmbiguityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="pwf-session-plan-"))
        self.root = self.tmp / "project"
        self.root.mkdir()
        self.cache = self.tmp / "cache"
        self.cache.mkdir()
        self.env = os.environ.copy()
        for key in (
            "PLAN_ID",
            "PWF_PLAN_ROOT",
            "PWF_SESSION_ID",
            "PWF_SESSION_KEY",
            "PLANNING_DISABLED",
        ):
            self.env.pop(key, None)
        self.env.update(
            PWF_TRUSTED_PYTHON=str(Path(sys.executable).resolve()),
            PYTHON_BIN=str(Path(sys.executable).resolve()),
            XDG_CACHE_HOME=str(self.cache),
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_scoped_plan(self, slug: str, marker: str) -> None:
        plan = self.root / ".planning" / slug
        plan.mkdir(parents=True, exist_ok=True)
        (plan / "task_plan.md").write_text(
            f"# {marker}\n\n### Phase 1: Work\n- **Status:** in_progress\n",
            encoding="utf-8",
        )
        (plan / "progress.md").write_text("# Progress\n", encoding="utf-8")

    def write_root_plan(self) -> None:
        (self.root / "task_plan.md").write_text(
            "# ROOT-PLAN\n\n### Phase 1: Work\n- **Status:** in_progress\n",
            encoding="utf-8",
        )
        (self.root / "progress.md").write_text("# Progress\n", encoding="utf-8")

    def point(self, slug: str) -> None:
        planning = self.root / ".planning"
        planning.mkdir(exist_ok=True)
        (planning / ".active_plan").write_text(slug + "\n", encoding="utf-8")

    def attach(self, session_id: str) -> None:
        sessions = self.root / ".planning" / "sessions"
        sessions.mkdir(parents=True, exist_ok=True)
        (sessions / f"{session_key(self.root, session_id)}.attached").write_text(
            "attached\n", encoding="utf-8"
        )
        # The generic injector uses a different portable digest. A validated
        # raw sentinel is intentionally supported by both routes.
        (sessions / f"{session_id}.attached").write_text("attached\n", encoding="utf-8")

    def native(
        self,
        script: str,
        *,
        session_id: str = "alpha",
        runner_arg: str | None = None,
        env_extra: dict[str, str] | None = None,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = dict(self.env)
        if env_extra:
            env.update(env_extra)
        command = [sys.executable, str(HOOKS / script)]
        if runner_arg:
            command.append(runner_arg)
        actual_cwd = cwd or self.root
        payload = {
            "cwd": str(actual_cwd),
            "session_id": session_id,
            "tool_input": {"command": "pwd"},
            "tool_response": "ok",
            "stop_hook_active": False,
        }
        return subprocess.run(
            command,
            input=json.dumps(payload),
            cwd=actual_cwd,
            text=True,
            encoding="utf-8",
            capture_output=True,
            env=env,
            check=False,
        )

    def generic(
        self,
        context: str,
        *,
        session_id: str = "alpha",
        env_extra: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = dict(self.env)
        env["PWF_SESSION_ID"] = session_id
        if env_extra:
            env.update(env_extra)
        return subprocess.run(
            ["sh", str(INJECT_PLAN), f"--context={context}"],
            cwd=self.root,
            text=True,
            encoding="utf-8",
            capture_output=True,
            env=env,
            check=False,
        )

    def direct_user_prompt(
        self,
        *,
        session_id: str = "alpha",
        env_extra: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = dict(self.env)
        env["PWF_SESSION_ID"] = session_id
        if env_extra:
            env.update(env_extra)
        return subprocess.run(
            ["sh", str(HOOKS / "user-prompt-submit.sh")],
            cwd=self.root,
            text=True,
            encoding="utf-8",
            capture_output=True,
            env=env,
            check=False,
        )

    def build_two_plan_tree(self) -> None:
        self.write_scoped_plan("plan-a", "PLAN-A")
        self.write_scoped_plan("plan-b", "PLAN-B")
        self.point("plan-a")
        self.attach("alpha")
        self.attach("beta")

    def test_two_sessions_refuse_both_pointers_until_distinct_plan_ids(self) -> None:
        self.build_two_plan_tree()
        for pointer in ("plan-a", "plan-b"):
            self.point(pointer)
            for session_id in ("alpha", "beta"):
                with self.subTest(pointer=pointer, session=session_id):
                    result = self.native(
                        "run_sh.py", session_id=session_id,
                        runner_arg="user-prompt-submit.sh",
                    )
                    self.assertEqual(0, result.returncode, result.stderr)
                    context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
                    self.assertIn(NOTICE, context)
                    self.assertNotIn("PLAN-A", context)
                    self.assertNotIn("PLAN-B", context)

        alpha = self.native(
            "run_sh.py", session_id="alpha", runner_arg="user-prompt-submit.sh",
            env_extra={"PLAN_ID": "plan-a"},
        )
        beta = self.native(
            "run_sh.py", session_id="beta", runner_arg="user-prompt-submit.sh",
            env_extra={"PLAN_ID": "plan-b"},
        )
        self.assertIn("PLAN-A", alpha.stdout)
        self.assertNotIn("PLAN-B", alpha.stdout)
        self.assertIn("PLAN-B", beta.stdout)
        self.assertNotIn("PLAN-A", beta.stdout)

    def test_root_plus_slug_is_ambiguous_on_all_user_prompt_routes(self) -> None:
        self.write_root_plan()
        self.write_scoped_plan("plan-a", "PLAN-A")
        self.attach("alpha")
        invocations = (
            lambda: self.native("run_sh.py", runner_arg="user-prompt-submit.sh"),
            self.direct_user_prompt,
            lambda: self.generic("userprompt"),
        )
        for invoke in invocations:
            result = invoke()
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn(NOTICE, result.stdout)
            self.assertNotIn("ROOT-PLAN", result.stdout)
            self.assertNotIn("PLAN-A", result.stdout)

    def test_all_native_events_refuse_ambiguous_unbound_plan(self) -> None:
        self.build_two_plan_tree()
        routes = (
            ("run_sh.py", "user-prompt-submit.sh"),
            ("run_sh.py", "session-start.sh"),
            ("run_sh.py", "pre-compact.sh"),
            ("pre_tool_use.py", None),
            ("permission_request.py", None),
            ("post_tool_use.py", None),
            ("stop.py", None),
        )
        for script, arg in routes:
            with self.subTest(script=script, arg=arg):
                result = self.native(script, runner_arg=arg)
                self.assertEqual(0, result.returncode, result.stderr)
                if arg == "user-prompt-submit.sh":
                    context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
                    self.assertEqual(1, context.count(NOTICE))
                    self.assertNotIn("PLAN-A", context)
                    self.assertNotIn("PLAN-B", context)
                else:
                    self.assertEqual("", result.stdout.strip())

    def test_generic_contexts_use_the_same_notice_rule(self) -> None:
        self.build_two_plan_tree()
        for context in ("userprompt", "pretool", "precompact"):
            result = self.generic(context)
            self.assertEqual(0, result.returncode, result.stderr)
            if context == "userprompt":
                self.assertEqual(1, result.stdout.count(NOTICE))
            else:
                self.assertEqual("", result.stdout.strip())
            self.assertNotIn("PLAN-A", result.stdout)
            self.assertNotIn("PLAN-B", result.stdout)

    def test_plan_root_pin_alone_does_not_select_a_same_root_plan(self) -> None:
        self.build_two_plan_tree()
        result = self.native(
            "run_sh.py", runner_arg="user-prompt-submit.sh", cwd=self.tmp,
            env_extra={"PWF_PLAN_ROOT": str(self.root)},
        )
        self.assertEqual(0, result.returncode, result.stderr)
        context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn(NOTICE, context)
        self.assertNotIn("PLAN-A", context)
        self.assertNotIn("PLAN-B", context)

    def test_single_plan_and_no_sessions_legacy_resolution_still_work(self) -> None:
        self.write_scoped_plan("plan-a", "PLAN-A")
        self.point("plan-a")
        self.attach("alpha")
        armed = self.native("run_sh.py", runner_arg="user-prompt-submit.sh")
        self.assertIn("PLAN-A", armed.stdout)

        shutil.rmtree(self.root / ".planning" / "sessions")
        self.write_scoped_plan("plan-b", "PLAN-B")
        self.point("plan-b")
        legacy = self.native(
            "run_sh.py", session_id="unattached", runner_arg="user-prompt-submit.sh"
        )
        self.assertIn(NOTICE, legacy.stdout)
        self.assertNotIn("PLAN-B", legacy.stdout)

    def test_unarmed_sessions_refuse_every_native_event_after_pointer_changes(self) -> None:
        self.write_scoped_plan("plan-a", "PLAN-A")
        self.write_scoped_plan("plan-b", "PLAN-B")
        routes = (
            ("run_sh.py", "user-prompt-submit.sh"),
            ("run_sh.py", "session-start.sh"),
            ("run_sh.py", "pre-compact.sh"),
            ("pre_tool_use.py", None),
            ("permission_request.py", None),
            ("post_tool_use.py", None),
            ("stop.py", None),
        )
        for pointer in ("plan-a", "plan-b"):
            self.point(pointer)
            for script, arg in routes:
                with self.subTest(pointer=pointer, script=script, arg=arg):
                    result = self.native(script, runner_arg=arg)
                    self.assertEqual(0, result.returncode, result.stderr)
                    if arg == "user-prompt-submit.sh":
                        self.assertIn(NOTICE, result.stdout)
                    else:
                        self.assertEqual("", result.stdout.strip())
                    self.assertNotIn("PLAN-A", result.stdout)
                    self.assertNotIn("PLAN-B", result.stdout)

        for plan_id, marker in (("plan-a", "PLAN-A"), ("plan-b", "PLAN-B")):
            result = self.native(
                "run_sh.py", runner_arg="user-prompt-submit.sh",
                env_extra={"PLAN_ID": plan_id},
            )
            self.assertIn(marker, result.stdout)
            self.assertNotIn(NOTICE, result.stdout)

    def test_unattached_session_keeps_existing_isolation_refusal(self) -> None:
        self.build_two_plan_tree()
        result = self.direct_user_prompt(session_id="unattached")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("Session isolation is armed", result.stdout)
        self.assertNotIn(NOTICE, result.stdout)
        self.assertNotIn("PLAN-A", result.stdout)
        self.assertNotIn("PLAN-B", result.stdout)

    def test_validation_context_accepts_only_a_selected_contained_plan(self) -> None:
        self.build_two_plan_tree()
        accepted = self.generic("validate", env_extra={"PLAN_ID": "plan-a"})
        ambiguous = self.generic("validate")
        missing = self.generic("validate", env_extra={"PLAN_ID": "missing"})
        unattached = self.generic("validate", session_id="unattached")
        self.assertEqual(VALIDATION_TOKEN, accepted.stdout.strip())
        for refused in (ambiguous, missing, unattached):
            self.assertNotIn(VALIDATION_TOKEN, refused.stdout)

        outside = self.tmp / "outside.md"
        outside.write_text("# OUTSIDE\n", encoding="utf-8")
        plan = self.root / ".planning" / "plan-a" / "task_plan.md"
        plan.unlink()
        try:
            plan.symlink_to(outside)
        except OSError:
            return
        escaped = self.generic("validate", env_extra={"PLAN_ID": "plan-a"})
        self.assertNotIn(VALIDATION_TOKEN, escaped.stdout)

    def test_preflight_rejects_bad_state_before_session_identity(self) -> None:
        self.write_scoped_plan("plan-a", "PLAN-A")
        self.point("plan-a")
        accepted = self.generic("preflight", session_id="unattached")
        self.assertEqual(PREFLIGHT_TOKEN, accepted.stdout.strip())

        missing = self.generic("preflight", env_extra={"PLAN_ID": "missing"})
        disabled = self.generic("preflight", env_extra={"PLANNING_DISABLED": "1"})
        bad_pin = self.generic("preflight", env_extra={"PWF_PLAN_ROOT": "relative"})
        for refused in (missing, disabled, bad_pin):
            self.assertEqual("", refused.stdout.strip())

        outside = self.tmp / "outside.md"
        outside.write_text("# OUTSIDE\n", encoding="utf-8")
        plan = self.root / ".planning" / "plan-a" / "task_plan.md"
        plan.unlink()
        no_plan = self.generic("preflight")
        self.assertNotIn(PREFLIGHT_TOKEN, no_plan.stdout)
        try:
            plan.symlink_to(outside)
        except OSError:
            return
        escaped = self.generic("preflight", env_extra={"PLAN_ID": "plan-a"})
        self.assertNotIn(PREFLIGHT_TOKEN, escaped.stdout)

    def test_native_post_tool_nudge_rearms_the_same_session_slot(self) -> None:
        self.write_scoped_plan("plan-a", "PLAN-A")
        self.point("plan-a")
        self.attach("alpha")
        self.attach("beta")

        first = self.native("post_tool_use.py", session_id="alpha")
        repeated = self.native("post_tool_use.py", session_id="alpha")
        prompt = self.native(
            "run_sh.py", session_id="alpha", runner_arg="user-prompt-submit.sh"
        )
        rearmed = self.native("post_tool_use.py", session_id="alpha")
        beta = self.native("post_tool_use.py", session_id="beta")

        self.assertIn("PostToolUse", first.stdout)
        self.assertEqual("", repeated.stdout.strip())
        self.assertIn("PLAN-A", prompt.stdout)
        self.assertIn("PostToolUse", rearmed.stdout)
        self.assertIn("PostToolUse", beta.stdout)


if __name__ == "__main__":
    unittest.main()
