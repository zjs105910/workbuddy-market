"""Nested plan-root isolation tests for scripts/inject-plan.sh (issue #212).

The reported failure mode: a Codex thread's cwd is a shared parent (/workspace)
while the real work lives in a nested project (/workspace/project) that has its
own .planning/.active_plan. Resolution ran purely relative to the process cwd,
so the parent's plan was injected on every hook fire and the nested project's
plan was never seen. There was also no session-attachment guard on this route,
unlike the Codex adapter (.codex/hooks/user-prompt-submit.sh).

Three behaviors under test, all in inject-plan.sh:

  * PWF_PLAN_ROOT — absolute plan-root binding, highest precedence. Pins a
    thread to a specific project root; a broken pin fails CLOSED (one notice,
    nothing injected) instead of silently falling back to the ambiguous cwd.
  * Session-attachment guard — when <root>/.planning/sessions exists, only
    sessions holding an .attached sentinel receive plan context; everyone else
    exits with completely empty output. No sessions dir = legacy, unchanged.
  * Nested-root conflict detection — when the plan was chosen by a cwd GUESS
    (active-plan pointer / newest-by-mtime / legacy root) and a direct child of
    the root carries its own LIVE competing plan (a .planning slug dir with
    task_plan.md), nothing is injected in ANY context; the one-line warning
    naming the nested root plus both escape hatches (PWF_PLAN_ROOT / PLAN_ID)
    is emitted for userprompt only, once per turn. Dead nested state (an empty
    or dangling .active_plan pointer) does not compete. Explicit resolution
    skips the check entirely.

Tree used throughout (the reporter's shape):

    workspace/.planning/plan-a            (active via .active_plan)
    workspace/project/.planning/plan-b    (active via its own .active_plan)
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = REPO_ROOT / "skills" / "planning-with-files"
INJECT_PLAN = SKILL_DIR / "scripts" / "inject-plan.sh"
PLAN_DOCTOR = SKILL_DIR / "scripts" / "plan-doctor.sh"

PLAN_A_TITLE = "PLAN-ALPHA-PARENT-WORKSPACE"
PLAN_B_TITLE = "PLAN-BRAVO-NESTED-PROJECT"


def have_sh() -> bool:
    return shutil.which("sh") is not None


@unittest.skipUnless(have_sh(), "sh not available on this platform")
class _WorkspaceFixtureTestCase(unittest.TestCase):
    """Shared parent/nested-project tree, env scrub, and script runners."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="pwf-nested-"))
        self.cache_dir = self.tmp / "_xdg_cache"
        self.cache_dir.mkdir()
        self.home_dir = self.tmp / "_home"
        self.home_dir.mkdir()
        self.workspace = self.tmp / "workspace"
        self.project = self.workspace / "project"
        self.env = os.environ.copy()
        self.env["CLAUDE_SKILL_DIR"] = str(SKILL_DIR)
        self.env["XDG_CACHE_HOME"] = str(self.cache_dir)
        self.env["HOME"] = str(self.home_dir)
        self.env["PWF_TRUSTED_PYTHON"] = str(Path(sys.executable).resolve())
        # Scrub every knob the script reads so the host env cannot leak in.
        for var in (
            "PLAN_ID",
            "PWF_PLAN_ROOT",
            "PWF_SESSION_ID",
            "PWF_SESSION_KEY",
            "PWF_INJECT",
            "PLANNING_DISABLED",
        ):
            self.env.pop(var, None)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- helpers ----------------------------------------------------------
    def build_tree(self, nested: bool = True) -> None:
        """Parent workspace with an active plan-a; optionally the nested
        project below it with its own active plan-b."""
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
            (plan_b / "task_plan.md").write_text(
                f"# {PLAN_B_TITLE}\n", encoding="utf-8"
            )
            (plan_b / "progress.md").write_text("# progress b\n", encoding="utf-8")
            (self.project / ".planning" / ".active_plan").write_text(
                "plan-b\n", encoding="utf-8"
            )

    def _run(
        self,
        context: str = "userprompt",
        env_extra: dict[str, str] | None = None,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = dict(self.env)
        if env_extra:
            env.update(env_extra)
        return subprocess.run(
            ["sh", str(INJECT_PLAN), f"--context={context}"],
            cwd=str(cwd if cwd is not None else self.workspace),
            text=True,
            encoding="utf-8",
            capture_output=True,
            env=env,
            check=False,
        )

    def _session_digest(self, session_id: str) -> str:
        digest = hashlib.sha256()
        project = os.path.normcase(os.path.realpath(os.path.abspath(self.workspace))).replace("\\", "/")
        for value in ("portable", project, session_id):
            encoded = value.encode("utf-8", errors="surrogatepass")
            digest.update(len(encoded).to_bytes(8, "big"))
            digest.update(encoded)
        return digest.hexdigest()

    def _attach(self, session_id: str) -> None:
        sessions = self.workspace / ".planning" / "sessions"
        sessions.mkdir(exist_ok=True)
        (sessions / f"{self._session_digest(session_id)}.attached").write_text("", encoding="utf-8")

    def _attach_raw(self, session_id: str) -> None:
        sessions = self.workspace / ".planning" / "sessions"
        sessions.mkdir(exist_ok=True)
        (sessions / f"{session_id}.attached").write_text("", encoding="utf-8")


class NestedPlanIsolationTests(_WorkspaceFixtureTestCase):
    # -- 1. ambiguous parent cwd: fail closed ------------------------------
    def test_parent_cwd_with_nested_plan_injects_nothing(self) -> None:
        self.build_tree(nested=True)
        result = self._run("userprompt")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertNotIn(PLAN_A_TITLE, result.stdout, "parent plan body must not inject")
        self.assertNotIn(PLAN_B_TITLE, result.stdout, "nested plan body must not inject")
        self.assertIn("Ambiguous plan", result.stdout)
        self.assertIn("project", result.stdout, "warning must name the nested root")
        # Both escape hatches must be named so the fix is obvious.
        self.assertIn("PWF_PLAN_ROOT", result.stdout)
        self.assertIn("PLAN_ID", result.stdout)

    # -- 2. PWF_PLAN_ROOT pins the nested project --------------------------
    def test_plan_root_pin_from_parent_cwd_injects_nested_plan(self) -> None:
        self.build_tree(nested=True)
        result = self._run(
            "userprompt", env_extra={"PWF_PLAN_ROOT": str(self.project)}
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn(PLAN_B_TITLE, result.stdout, "pinned root's plan must inject")
        self.assertNotIn(PLAN_A_TITLE, result.stdout, "parent plan must not leak through")
        self.assertIn("ACTIVE PLAN", result.stdout)

    # -- 3. broken pin fails closed, never falls back ----------------------
    def test_plan_root_broken_pin_notices_and_injects_nothing(self) -> None:
        self.build_tree(nested=True)
        result = self._run(
            "userprompt",
            env_extra={"PWF_PLAN_ROOT": str(self.workspace / "does-not-exist")},
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertNotEqual("", result.stdout.strip(), "broken pin must emit a notice")
        self.assertIn("PWF_PLAN_ROOT", result.stdout)
        self.assertNotIn(PLAN_A_TITLE, result.stdout, "must not fall back to cwd plan")
        self.assertNotIn(PLAN_B_TITLE, result.stdout)

    # -- 4. explicit PLAN_ID beats the conflict check ----------------------
    def test_valid_plan_id_at_parent_still_injects_despite_nested_plan(self) -> None:
        self.build_tree(nested=True)
        result = self._run("userprompt", env_extra={"PLAN_ID": "plan-a"})
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn(
            PLAN_A_TITLE,
            result.stdout,
            "explicit PLAN_ID names the plan deliberately; conflict check must not fire",
        )
        self.assertNotIn("Ambiguous plan", result.stdout)

    # -- 5. sessions dir + unattached session: completely silent -----------
    def test_unattached_session_injects_no_plan_but_says_why(self) -> None:
        self.build_tree(nested=False)
        (self.workspace / ".planning" / "sessions").mkdir()
        result = self._run("userprompt", env_extra={"PWF_SESSION_ID": "sess-1"})
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertNotIn("BEGIN PLAN DATA", result.stdout)
        self.assertNotIn("PLAN-A-MARKER", result.stdout)
        self.assertIn("Session isolation is armed", result.stdout)

    def test_sessions_dir_with_empty_session_id_says_why(self) -> None:
        # Same guard, other arm: the sessions dir exists but the caller carries
        # no session ID at all. This is the arm that fires on every host which
        # never sets PWF_SESSION_ID, so silence here would strand a user with a
        # stale sessions dir and no symptom to search for. Injection is still
        # refused; it just announces itself.
        self.build_tree(nested=False)
        (self.workspace / ".planning" / "sessions").mkdir()
        result = self._run("userprompt")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertNotIn("BEGIN PLAN DATA", result.stdout)
        self.assertIn("Session isolation is armed", result.stdout)
        # The notice must name both recovery routes.
        self.assertIn("PWF_SESSION_ID", result.stdout)
        self.assertIn("delete", result.stdout)

    def test_unattached_session_notice_does_not_repeat_per_tool_call(self) -> None:
        # PreToolUse fires on every matched tool call. A per-call notice would
        # be spam, so the guard stays silent there while still refusing.
        self.build_tree(nested=False)
        (self.workspace / ".planning" / "sessions").mkdir()
        result = self._run("pretool")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stdout)

    # -- 6. attached session injects ---------------------------------------
    def test_attached_session_injects_plan(self) -> None:
        self.build_tree(nested=False)
        self._attach("sess-1")
        result = self._run("userprompt", env_extra={"PWF_SESSION_ID": "sess-1"})
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn(PLAN_A_TITLE, result.stdout, "attached session must receive the plan")

    def test_safe_legacy_raw_session_sentinel_remains_compatible(self) -> None:
        self.build_tree(nested=False)
        session_id = "Legacy_1.safe-raw"
        self._attach_raw(session_id)

        result = self._run("userprompt", env_extra={"PWF_SESSION_ID": session_id})

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn(PLAN_A_TITLE, result.stdout)

    def test_legacy_raw_session_id_length_boundary_is_exact(self) -> None:
        self.build_tree(nested=False)
        accepted = "a" * 128
        rejected = "b" * 129
        self._attach_raw(accepted)
        self._attach_raw(rejected)

        accepted_result = self._run("userprompt", env_extra={"PWF_SESSION_ID": accepted})
        rejected_result = self._run("userprompt", env_extra={"PWF_SESSION_ID": rejected})

        self.assertIn(PLAN_A_TITLE, accepted_result.stdout)
        self.assertNotIn(PLAN_A_TITLE, rejected_result.stdout)

    def test_hostile_control_id_raw_sentinel_is_rejected_but_digest_works(self) -> None:
        self.build_tree(nested=False)
        session_id = "hostile session"
        self._attach_raw(session_id)

        raw_only = self._run("userprompt", env_extra={"PWF_SESSION_ID": session_id})
        self.assertNotIn(PLAN_A_TITLE, raw_only.stdout)

        self._attach(session_id)
        digest_attached = self._run("userprompt", env_extra={"PWF_SESSION_ID": session_id})
        self.assertIn(PLAN_A_TITLE, digest_attached.stdout)

    def test_path_traversal_id_cannot_use_out_of_directory_raw_sentinel(self) -> None:
        self.build_tree(nested=False)
        sessions = self.workspace / ".planning" / "sessions"
        sessions.mkdir(exist_ok=True)
        (sessions.parent / "escape.attached").write_text("", encoding="utf-8")

        result = self._run("userprompt", env_extra={"PWF_SESSION_ID": "../escape"})

        self.assertNotIn(PLAN_A_TITLE, result.stdout)

    def test_stale_ambient_session_key_cannot_attach_current_session(self) -> None:
        self.build_tree(nested=False)
        stale_id = "old-session"
        current_id = "current-session"
        self._attach(stale_id)

        result = self._run(
            "userprompt",
            env_extra={
                "PWF_SESSION_ID": current_id,
                "PWF_SESSION_KEY": self._session_digest(stale_id),
            },
        )

        self.assertNotIn(PLAN_A_TITLE, result.stdout)
        self.assertIn("Session isolation is armed", result.stdout)

    def test_raw_session_sentinel_symlink_is_rejected_when_supported(self) -> None:
        self.build_tree(nested=False)
        session_id = "safe-session"
        sessions = self.workspace / ".planning" / "sessions"
        sessions.mkdir(exist_ok=True)
        outside = self.tmp / "outside-attached"
        outside.write_text("", encoding="utf-8")
        try:
            (sessions / f"{session_id}.attached").symlink_to(outside)
        except OSError as exc:
            self.skipTest(f"file symlinks unavailable: {exc}")

        result = self._run("userprompt", env_extra={"PWF_SESSION_ID": session_id})

        self.assertNotIn(PLAN_A_TITLE, result.stdout)

    @unittest.skipUnless(os.name == "nt", "Windows junction containment contract")
    def test_sessions_directory_junction_redirection_is_rejected(self) -> None:
        self.build_tree(nested=False)
        session_id = "safe-session"
        sessions = self.workspace / ".planning" / "sessions"
        outside = self.tmp / "outside-sessions"
        outside.mkdir()
        (outside / f"{session_id}.attached").write_text("", encoding="utf-8")
        created = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(sessions), str(outside)],
            text=True,
            capture_output=True,
            check=False,
        )
        if created.returncode != 0:
            self.skipTest(f"junction creation unavailable: {created.stderr}")
        try:
            result = self._run("userprompt", env_extra={"PWF_SESSION_ID": session_id})
            self.assertNotIn(PLAN_A_TITLE, result.stdout)
            self.assertIn("Session isolation is armed", result.stdout)
        finally:
            subprocess.run(
                ["cmd.exe", "/d", "/c", "rmdir", str(sessions)],
                capture_output=True,
                check=False,
            )

    def test_attached_session_does_not_bypass_nested_conflict_check(self) -> None:
        # Attachment admits the session to plan context but does not select a
        # plan. A competing nested plan must still suppress the parent's plan.
        self.build_tree(nested=True)
        self._attach("sess-1")
        result = self._run("userprompt", env_extra={"PWF_SESSION_ID": "sess-1"})
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertNotIn(PLAN_A_TITLE, result.stdout)
        self.assertNotIn(PLAN_B_TITLE, result.stdout)
        self.assertIn("Ambiguous plan", result.stdout)

    # -- 7. legacy invariant: no nesting = unchanged injection -------------
    def test_no_nested_plan_injects_exactly_as_before(self) -> None:
        self.build_tree(nested=False)
        result = self._run("userprompt")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("ACTIVE PLAN", result.stdout)
        self.assertIn(PLAN_A_TITLE, result.stdout)
        self.assertIn("===BEGIN-PWF-DATA kind=plan nonce=", result.stdout)
        self.assertIn("===END-PWF-DATA kind=plan nonce=", result.stdout)
        self.assertNotIn("Ambiguous plan", result.stdout)

    def test_nested_planning_without_competing_plan_is_no_conflict(self) -> None:
        # A bare nested .planning dir (no .active_plan, no <slug>/task_plan.md)
        # is not a competing plan; the parent must keep injecting normally.
        self.build_tree(nested=False)
        (self.project / ".planning").mkdir(parents=True)
        result = self._run("userprompt")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn(PLAN_A_TITLE, result.stdout)
        self.assertNotIn("Ambiguous plan", result.stdout)

    # -- 8. PLANNING_DISABLED still silences everything --------------------
    def test_planning_disabled_silences_everything(self) -> None:
        self.build_tree(nested=True)
        result = self._run("userprompt", env_extra={"PLANNING_DISABLED": "1"})
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stdout)
        # Also with a broken pin: the opt-out is checked first.
        result = self._run(
            "userprompt",
            env_extra={
                "PLANNING_DISABLED": "1",
                "PWF_PLAN_ROOT": str(self.workspace / "does-not-exist"),
            },
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stdout)

    # -- 9. pretool context: same guard, same fail-closed ------------------
    def test_pretool_obeys_session_guard(self) -> None:
        self.build_tree(nested=False)
        (self.workspace / ".planning" / "sessions").mkdir()
        result = self._run("pretool", env_extra={"PWF_SESSION_ID": "sess-1"})
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stdout, "pretool must obey the session guard")

    def test_pretool_obeys_conflict_fail_closed(self) -> None:
        # PreToolUse fires on every matched tool call (and autonomous mode
        # drops per-tool-call injection entirely), so the ambiguity NOTICE is
        # turn-scoped to userprompt, same shape as the session guard. The
        # REFUSAL still applies here: no plan body, and no notice spam either.
        self.build_tree(nested=True)
        result = self._run("pretool")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            "", result.stdout, "pretool must refuse silently under ambiguity"
        )
        # precompact carries no plan body and is equally turn-silent.
        result = self._run("precompact")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            "", result.stdout, "precompact must refuse silently under ambiguity"
        )

    # -- 10. dead nested pointers are not competing plans ------------------
    def test_nested_empty_active_plan_is_not_competing(self) -> None:
        # An empty .active_plan resolves to nothing for a thread inside the
        # nested project (its own injection bails at the task_plan.md check),
        # so it must not permanently kill injection at this root.
        self.build_tree(nested=False)
        (self.project / ".planning").mkdir(parents=True)
        (self.project / ".planning" / ".active_plan").write_text(
            "", encoding="utf-8"
        )
        result = self._run("userprompt")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn(PLAN_A_TITLE, result.stdout, "parent plan must keep injecting")
        self.assertNotIn("Ambiguous plan", result.stdout)

    def test_nested_dangling_active_plan_is_not_competing(self) -> None:
        # A pointer naming a slug dir deleted long ago is dead state, not a
        # competing plan.
        self.build_tree(nested=False)
        (self.project / ".planning").mkdir(parents=True)
        (self.project / ".planning" / ".active_plan").write_text(
            "deleted-long-ago\n", encoding="utf-8"
        )
        result = self._run("userprompt")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn(PLAN_A_TITLE, result.stdout, "parent plan must keep injecting")
        self.assertNotIn("Ambiguous plan", result.stdout)

    def test_nested_live_plan_without_pointer_still_conflicts(self) -> None:
        # The conflict check relies on the <slug>/task_plan.md scan alone: a
        # live nested plan must still refuse injection at the parent even with
        # no .active_plan pointer, proving the pointer-branch removal did not
        # disable the feature.
        self.build_tree(nested=True)
        (self.project / ".planning" / ".active_plan").unlink()
        result = self._run("userprompt")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertNotIn(PLAN_A_TITLE, result.stdout)
        self.assertNotIn(PLAN_B_TITLE, result.stdout)
        self.assertIn("Ambiguous plan", result.stdout)

    # -- 11. pinned root + autonomous mode: ledger follows the pin ---------
    def _attest_and_arm_child(self) -> None:
        """Give the nested plan-b phase structure, an attestation, and
        autonomous mode; give the parent plan-a a COMPLETED phase and its own
        ledger so a parent leak is unmistakable in the ledger block."""
        plan_a = self.workspace / ".planning" / "plan-a"
        (plan_a / "task_plan.md").write_bytes(
            (
                f"# {PLAN_A_TITLE}\n"
                "### Phase 1: Parent finished\n"
                "- **Status:** complete\n"
            ).encode("utf-8")
        )
        (plan_a / "ledger-parentagent.jsonl").write_text(
            '{"tick": 1, "event": "parent_evt"}\n', encoding="utf-8"
        )
        plan_b = self.project / ".planning" / "plan-b"
        child_body = (
            f"# {PLAN_B_TITLE}\n"
            "### Phase 1: Child build\n"
            "- **Status:** in_progress\n"
        ).encode("utf-8")
        (plan_b / "task_plan.md").write_bytes(child_body)
        (plan_b / ".attestation").write_text(
            hashlib.sha256(child_body).hexdigest(), encoding="utf-8"
        )
        (plan_b / ".mode").write_text("autonomous\n", encoding="utf-8")
        (plan_b / "ledger-childagent.jsonl").write_text(
            '{"tick": 1, "event": "child_evt"}\n', encoding="utf-8"
        )

    def test_pinned_autonomous_ledger_reports_pinned_plan_not_parent(self) -> None:
        # Defect class: the plan BODY honoured the pin while the ledger block
        # shelled ledger-summary.sh with no argument, which re-resolved from
        # the process cwd — child plan body over parent phase counts. The
        # parent's "phases: 1/1 complete" + "in_progress: none" reads as a
        # termination signal to an autonomous loop working the child plan.
        self.build_tree(nested=True)
        self._attest_and_arm_child()
        result = self._run(
            "userprompt", env_extra={"PWF_PLAN_ROOT": str(self.project)}
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn(PLAN_B_TITLE, result.stdout)
        self.assertNotIn(PLAN_A_TITLE, result.stdout)
        self.assertIn("===BEGIN-PWF-DATA kind=progress nonce=", result.stdout)
        self.assertIn("=== RUN LEDGER ===", result.stdout)
        self.assertIn(
            "phases: 0/1 complete",
            result.stdout,
            "ledger block must count the PINNED plan's phases",
        )
        self.assertIn("in_progress: ### Phase 1: Child build", result.stdout)
        self.assertNotIn(
            "phases: 1/1 complete",
            result.stdout,
            "parent's phase counts leaked into the pinned thread",
        )
        self.assertIn("agent childagent: child_evt", result.stdout)
        self.assertNotIn(
            "parentagent",
            result.stdout,
            "parent's agent events leaked into the pinned thread",
        )

    # -- 12. Attestation has no reusable digest trust cache ----------------
    def test_pinned_plan_uses_no_trusted_hash_cache_across_cwds(self) -> None:
        # Attestation hashes a private snapshot on every fire. Caller cwd must
        # not create, select, or reuse a digest cache slot.
        self.build_tree(nested=True)
        self._attest_and_arm_child()
        pin = {"PWF_PLAN_ROOT": str(self.project)}
        first = self._run("userprompt", env_extra=pin)
        second = self._run("userprompt", env_extra=pin, cwd=self.tmp)
        self.assertIn(PLAN_B_TITLE, first.stdout, first.stdout)
        self.assertIn(PLAN_B_TITLE, second.stdout, second.stdout)
        self.assertFalse((self.cache_dir / "pwf-sha").exists())
        snapshots = self.cache_dir / "pwf-snapshots"
        self.assertTrue(snapshots.is_dir())
        self.assertEqual([], list(snapshots.iterdir()))


class PlanDoctorRefusalStateTests(_WorkspaceFixtureTestCase):
    """plan-doctor must not report a refusal notice as PASS.

    Defect: the doctor treated ANY non-empty output from the injection probe
    as success, so a user whose hooks were refusing to inject (session
    isolation armed, or nested-plan ambiguity) was told "PASS injection:
    emits plan context (N bytes)" when those bytes were the refusal notice —
    a green light from the one diagnostic tool a dark user is pointed at.
    """

    def _run_doctor(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["sh", str(PLAN_DOCTOR)],
            cwd=str(self.workspace),
            text=True,
            encoding="utf-8",
            capture_output=True,
            env=dict(self.env),
            check=False,
        )

    def test_doctor_reports_session_refusal_as_its_own_state(self) -> None:
        self.build_tree(nested=False)
        (self.workspace / ".planning" / "sessions").mkdir()
        result = self._run_doctor()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertNotIn(
            "PASS  injection",
            result.stdout,
            "a refusal notice must never be reported as PASS",
        )
        self.assertIn("session isolation", result.stdout)
        # The remedy must be actionable: both the attach route and the disarm
        # route.
        self.assertIn("PWF_SESSION_ID", result.stdout)
        self.assertIn(".planning/sessions", result.stdout)

    def test_doctor_reports_ambiguity_as_its_own_state(self) -> None:
        self.build_tree(nested=True)
        result = self._run_doctor()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertNotIn("PASS  injection", result.stdout)
        self.assertIn("PWF_PLAN_ROOT", result.stdout)

    def test_doctor_still_passes_on_healthy_injection(self) -> None:
        self.build_tree(nested=False)
        result = self._run_doctor()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("PASS  injection: emits plan context", result.stdout)


class TwoThreadSharedParentTests(_WorkspaceFixtureTestCase):
    """Issue #212 suggested fix 5, asserted as one scenario rather than two tests.

    The reported incident needs TWO threads to exist: one shared parent cwd,
    two nested projects with their own plans, and each thread having to receive
    its own plan and not the other's. Firing the script once and checking the
    happy path proves nothing about isolation, so both threads run against the
    same tree here and are asserted together.
    """

    def build_two_projects(self) -> tuple[Path, Path]:
        """Shared parent with its own plan, plus two sibling nested projects."""
        self.build_tree(nested=True)  # workspace plan-a + project/plan-b
        other = self.workspace / "other-project"
        plan_c = other / ".planning" / "plan-c"
        plan_c.mkdir(parents=True)
        (plan_c / "task_plan.md").write_text("# PLAN-CHARLIE-SECOND-PROJECT\n", encoding="utf-8")
        (plan_c / "progress.md").write_text("# progress c\n", encoding="utf-8")
        (other / ".planning" / ".active_plan").write_text("plan-c\n", encoding="utf-8")
        return self.project, other

    def test_two_threads_one_shared_cwd_each_get_their_own_plan(self) -> None:
        first, second = self.build_two_projects()

        # Both threads run with cwd at the shared parent, exactly as the
        # reporter's Codex threads did. Only the pin differs.
        thread_one = self._run("userprompt", env_extra={"PWF_PLAN_ROOT": str(first)})
        thread_two = self._run("userprompt", env_extra={"PWF_PLAN_ROOT": str(second)})

        self.assertEqual(0, thread_one.returncode, thread_one.stderr)
        self.assertEqual(0, thread_two.returncode, thread_two.stderr)

        # Each thread sees its own plan.
        self.assertIn(PLAN_B_TITLE, thread_one.stdout)
        self.assertIn("PLAN-CHARLIE-SECOND-PROJECT", thread_two.stdout)

        # Neither thread sees the other's plan, nor the shared parent's.
        self.assertNotIn("PLAN-CHARLIE-SECOND-PROJECT", thread_one.stdout)
        self.assertNotIn(PLAN_B_TITLE, thread_two.stdout)
        self.assertNotIn(PLAN_A_TITLE, thread_one.stdout)
        self.assertNotIn(PLAN_A_TITLE, thread_two.stdout)

    def test_unpinned_thread_beside_a_pinned_one_refuses_rather_than_guessing(self) -> None:
        first, _second = self.build_two_projects()

        pinned = self._run("userprompt", env_extra={"PWF_PLAN_ROOT": str(first)})
        unpinned = self._run("userprompt")

        # The pinned thread works. The unpinned one, facing two nested projects
        # from a shared cwd, refuses instead of picking one and being wrong for
        # at least one thread. That refusal is the whole point of the issue.
        self.assertIn(PLAN_B_TITLE, pinned.stdout)
        self.assertIn("Ambiguous plan", unpinned.stdout)
        self.assertNotIn(PLAN_A_TITLE, unpinned.stdout)
        self.assertNotIn(PLAN_B_TITLE, unpinned.stdout)

    def test_two_session_identities_one_tree_only_the_attached_one_sees_the_plan(self) -> None:
        # The session-attachment arm of the same scenario: two threads, one
        # cwd, distinct session ids, only one attached.
        self.build_tree(nested=False)
        self._attach("thread-one")

        attached = self._run("userprompt", env_extra={"PWF_SESSION_ID": "thread-one"})
        unattached = self._run("userprompt", env_extra={"PWF_SESSION_ID": "thread-two"})

        self.assertIn(PLAN_A_TITLE, attached.stdout)
        self.assertNotIn(PLAN_A_TITLE, unattached.stdout)
        self.assertIn("Session isolation is armed", unattached.stdout)


if __name__ == "__main__":
    unittest.main()
