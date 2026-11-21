"""An explicit PLAN_ID is a binding, not a hint (issue #237).

`commands/plan-attest.md` has promised since v3.9.0 that an explicit
`${PLAN_ID}` or `${PWF_PLAN_ROOT}` which does not resolve exits with an error
and never falls back to another plan. The `PWF_PLAN_ROOT` half held. The
`PLAN_ID` half did not: `resolve_from_env` returned 1 both when no selector was
set and when the selector was rejected, so a `PLAN_ID` of valid slug shape that
named no directory fell through to `.active_plan` and then to newest-by-mtime.
A one-character typo therefore attested a DIFFERENT plan at rc=0, injected it,
and pointed the session's edits at it.

These tests pin the fixed contract across every consumer that picks a plan:
the shared resolver, the inline resolver inside inject-plan.sh, attestation,
the completion gate, and the two scripts that WRITE into the selected plan
directory (phase-status, ledger-append). Each one must refuse rather than
substitute, and each one must say so rather than going quietly dark.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"

# A typo of "2026-07-21-alpha": valid slug shape, names no directory. This is
# the case the old test suite never covered, which is why the defect shipped.
TYPO_ID = "2026-07-21-alhpa"


def have_sh() -> bool:
    return shutil.which("sh") is not None


@unittest.skipUnless(have_sh(), "requires a POSIX sh")
class PlanSelectorBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile

        self.tempdir = tempfile.TemporaryDirectory(prefix="pwf-binding-")
        self.root = Path(self.tempdir.name)
        planning = self.root / ".planning"
        for slug in ("2026-07-21-alpha", "2026-07-21-beta"):
            d = planning / slug
            d.mkdir(parents=True)
            (d / "task_plan.md").write_text(f"# {slug}\n", encoding="utf-8")
        # The pointer names beta, so any fall-through lands on a real, wrong
        # plan rather than on nothing. Without this the assertions below could
        # pass for the wrong reason.
        (planning / ".active_plan").write_text("2026-07-21-beta\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _run(self, script: str, *args: str, plan_id: str | None = TYPO_ID):
        env = os.environ.copy()
        env.pop("PLAN_ID", None)
        env.pop("PWF_PLAN_ROOT", None)
        env.pop("PLANNING_DISABLED", None)
        if plan_id is not None:
            env["PLAN_ID"] = plan_id
        return subprocess.run(
            ["sh", str(SCRIPTS / script), *args],
            cwd=str(self.root),
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
        )

    # --- the resolver itself ------------------------------------------------

    def test_resolver_control_arm_resolves_the_real_slug(self):
        """The probe can return alpha, so a later empty result is a refusal."""
        out = self._run("resolve-plan-dir.sh", plan_id="2026-07-21-alpha").stdout.strip()
        self.assertTrue(out.endswith("2026-07-21-alpha"), out)

    def test_resolver_refuses_a_valid_shape_nonexistent_slug(self):
        self.assertEqual("", self._run("resolve-plan-dir.sh").stdout.strip())

    def test_resolver_refuses_a_traversal_shaped_slug(self):
        out = self._run("resolve-plan-dir.sh", plan_id="../outside").stdout.strip()
        self.assertEqual("", out)

    def test_resolver_exit_status_stays_zero_on_refusal(self):
        """Emptiness is the fail-closed signal; a non-zero status would kill
        callers running under set -e for a condition that is not an error."""
        self.assertEqual(0, self._run("resolve-plan-dir.sh").returncode)

    def test_empty_plan_id_is_not_a_selector(self):
        """init-session.sh passes PLAN_ID="" into attest-plan.sh on the legacy
        path, so an empty value must keep meaning "unset"."""
        # One live plan remains compatible; an empty pin cannot choose among two.
        (self.root / ".planning" / "2026-07-21-alpha" / "task_plan.md").unlink()
        out = self._run("resolve-plan-dir.sh", plan_id="").stdout.strip()
        self.assertTrue(out.endswith("2026-07-21-beta"), out)

    # --- attestation --------------------------------------------------------

    def test_attest_refuses_and_writes_no_attestation_anywhere(self):
        result = self._run("attest-plan.sh")
        self.assertNotEqual(0, result.returncode, result.stdout)
        self.assertIn("PLAN_ID", result.stderr)
        for slug in ("2026-07-21-alpha", "2026-07-21-beta"):
            self.assertFalse(
                (self.root / ".planning" / slug / ".attestation").exists(),
                f"attested {slug} through a rejected selector",
            )

    def test_attest_names_the_selector_rather_than_reporting_no_plan(self):
        """The generic "No task_plan.md found" sent operators after the wrong
        problem: the plan exists, the selector was refused."""
        stderr = self._run("attest-plan.sh").stderr
        self.assertIn(TYPO_ID, stderr)
        self.assertNotIn("Create a plan first", stderr)

    # --- injection ----------------------------------------------------------

    def test_injection_refuses_and_emits_no_plan_frame(self):
        result = self._run("inject-plan.sh", "--context=userprompt")
        self.assertNotIn("BEGIN-PWF-DATA", result.stdout)
        self.assertNotIn("2026-07-21-beta", result.stdout)
        self.assertIn("PLAN_ID does not name a plan directory", result.stdout)

    def test_injection_notice_is_userprompt_only(self):
        """pretool fires per tool call; repeating the notice there would spam
        the transcript with the same line."""
        result = self._run("inject-plan.sh", "--context=pretool")
        self.assertEqual("", result.stdout.strip())

    def test_injection_still_works_for_a_correct_selector(self):
        result = self._run("inject-plan.sh", "--context=userprompt",
                           plan_id="2026-07-21-alpha")
        self.assertIn("BEGIN-PWF-DATA", result.stdout)
        self.assertIn("2026-07-21-alpha", result.stdout)

    # --- consumers that read or write the selected plan ---------------------

    def test_check_complete_reads_no_other_plans_state(self):
        (self.root / "task_plan.md").write_text(
            "# root decoy\n### Phase 1\n**Status:** complete\n", encoding="utf-8"
        )
        result = self._run("check-complete.sh")
        self.assertIn("did not resolve", result.stdout)
        self.assertNotIn("complete", result.stdout.replace("did not resolve", ""))

    def test_phase_status_writes_into_no_other_plan(self):
        (self.root / "task_plan.md").write_text(
            "# root decoy\n### Phase 1\n**Status:** pending\n", encoding="utf-8"
        )
        before = (self.root / "task_plan.md").read_bytes()
        result = self._run("phase-status.sh", "1", "complete")
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(before, (self.root / "task_plan.md").read_bytes())

    def test_ledger_append_writes_into_no_other_plan(self):
        result = self._run("ledger-append.sh", "note", "hello")
        self.assertNotEqual(0, result.returncode)
        self.assertEqual([], sorted(self.root.glob("**/ledger-*.jsonl")))

    def test_ledger_summary_degrades_loudly_instead_of_counting_another_plan(self):
        (self.root / "task_plan.md").write_text(
            "# root decoy\n### Phase 1\n**Status:** complete\n", encoding="utf-8"
        )
        stdout = self._run("ledger-summary.sh").stdout
        self.assertIn("unavailable", stdout)
        self.assertNotIn("phases: 1/1 complete", stdout)


if __name__ == "__main__":
    unittest.main()
