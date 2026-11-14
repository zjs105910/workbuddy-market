"""A project's root .mode is a floor, not a default slug scope replaces (#238).

A project makes attestation mandatory by committing a root `.mode`
(`autonomous inject-smart`), a reviewed project setting. Creating a slug plan
silently exempted the session from it: inject-plan.sh read the SLUG's `.mode`
and never the root's, and init-session.sh writes no `.mode` unless
`--autonomous` or `--gated` was passed. So `init-session.sh <name>`, which
`/plan` runs, produced a plan with no mode, no attestation requirement and full
injection. The project's policy became a flag the agent chose at plan creation.

The fix reads strictness-RAISING tokens from either file (a slug may raise,
never lower) and honors the one strictness-LOWERING token, `plan-guard-off`,
only when the root carries it too. With no root `.mode` present the effective
token set is exactly the slug's, so existing projects are unchanged: the last
two tests pin that.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"
SLUG = "2026-09-02-arbtask"


def have_sh() -> bool:
    return shutil.which("sh") is not None


@unittest.skipUnless(have_sh(), "requires a POSIX sh")
class RootModeFloorTests(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile

        self.tempdir = tempfile.TemporaryDirectory(prefix="pwf-modefloor-")
        self.root = Path(self.tempdir.name)
        self.slug_dir = self.root / ".planning" / SLUG
        self.slug_dir.mkdir(parents=True)
        (self.root / "task_plan.md").write_text(
            "# root plan (project policy)\n", encoding="utf-8"
        )
        # An in_progress phase and a pending one, so an ARMED gate has
        # something to block on. With every phase complete the gate resolves to
        # advisory whether or not it is armed, and a gate assertion over that
        # fixture passes without testing anything.
        (self.slug_dir / "task_plan.md").write_text(
            "# slug plan\n"
            "### Phase 1\n**Status:** in_progress\n"
            "### Phase 2\n**Status:** pending\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _run(self, script: str, *args: str, env_extra: dict | None = None):
        env = os.environ.copy()
        for key in ("PLAN_ID", "PWF_PLAN_ROOT", "PLANNING_DISABLED", "PWF_INJECT",
                    "PWF_PLAN_GUARD"):
            env.pop(key, None)
        if env_extra:
            env.update(env_extra)
        return subprocess.run(
            ["sh", str(SCRIPTS / script), *args],
            cwd=str(self.root),
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
        )

    def _inject(self):
        return self._run("inject-plan.sh", "--context=userprompt").stdout

    def test_slug_without_mode_inherits_the_root_attestation_requirement(self):
        """The reported fixture: one slug directory turned the policy off."""
        (self.root / ".mode").write_text("autonomous inject-smart\n", encoding="utf-8")
        out = self._inject()
        self.assertIn("requires attested plan", out)
        self.assertNotIn("BEGIN-PWF-DATA", out)

    def test_attesting_the_slug_arms_injection_under_the_inherited_mode(self):
        """Fail-closed must not mean permanently dark: the documented remedy
        has to work."""
        (self.root / ".mode").write_text("autonomous inject-smart\n", encoding="utf-8")
        attest = self._run("attest-plan.sh", env_extra={"PLAN_ID": SLUG})
        self.assertEqual(0, attest.returncode, attest.stderr)
        self.assertIn("BEGIN-PWF-DATA", self._inject())

    def _gate(self) -> str:
        env = os.environ.copy()
        for key in ("PLAN_ID", "PWF_PLAN_ROOT", "PLANNING_DISABLED"):
            env.pop(key, None)
        return subprocess.run(
            ["sh", str(SCRIPTS / "check-complete.sh"), "--gate"],
            cwd=str(self.root), env=env, capture_output=True, text=True,
            timeout=180, stdin=subprocess.DEVNULL,
        ).stdout

    def test_gate_stays_advisory_when_no_mode_file_asks_for_it(self):
        """The negative control for the two gate tests below. Without it they
        would pass on a fixture where the gate can only ever be advisory."""
        self._run("attest-plan.sh", env_extra={"PLAN_ID": SLUG})
        self.assertNotIn('"decision":"block"', self._gate())

    def test_a_slug_may_raise_strictness_above_the_root(self):
        """gate in the slug survives a root that only asks for autonomous."""
        (self.root / ".mode").write_text("autonomous\n", encoding="utf-8")
        (self.slug_dir / ".mode").write_text("autonomous gate\n", encoding="utf-8")
        self._run("attest-plan.sh", env_extra={"PLAN_ID": SLUG})
        self.assertIn('"decision":"block"', self._gate())

    def _regress_the_plan(self) -> str:
        """Prime the parallel-write guard, then destroy checked work behind it.

        The guard fires on checked items or completed phases that vanished
        since the hooks last read the file, so the primed version must contain
        some. Returns the injection output of the fire that follows the loss.
        """
        (self.slug_dir / "task_plan.md").write_text(
            "# slug plan\n- [x] finished work\n### Phase 1\n**Status:** complete\n",
            encoding="utf-8",
        )
        self._run("attest-plan.sh", env_extra={"PLAN_ID": SLUG})
        self._inject()
        (self.slug_dir / "task_plan.md").write_text(
            "# slug plan\n- [ ] finished work\n### Phase 1\n**Status:** pending\n",
            encoding="utf-8",
        )
        self._run("attest-plan.sh", env_extra={"PLAN_ID": SLUG})
        return self._inject()

    def test_a_slug_cannot_lower_a_protection_the_root_kept_on(self):
        """plan-guard-off is the only strictness-lowering token. A root .mode
        without it means the slug alone cannot switch the parallel-write guard
        off."""
        (self.root / ".mode").write_text("autonomous\n", encoding="utf-8")
        (self.slug_dir / ".mode").write_text(
            "autonomous plan-guard-off\n", encoding="utf-8"
        )
        self.assertIn("PLAN REGRESSED", self._regress_the_plan())

    def test_plan_guard_off_still_works_when_the_root_agrees(self):
        (self.root / ".mode").write_text(
            "autonomous plan-guard-off\n", encoding="utf-8"
        )
        (self.slug_dir / ".mode").write_text(
            "autonomous plan-guard-off\n", encoding="utf-8"
        )
        self.assertNotIn("PLAN REGRESSED", self._regress_the_plan())

    def test_root_gate_token_arms_the_completion_gate_for_a_slug_plan(self):
        """The same bypass reached check-complete.sh's guard 1, which the issue
        did not test but which reads .mode the same way."""
        (self.root / ".mode").write_text("autonomous gate\n", encoding="utf-8")
        self._run("attest-plan.sh", env_extra={"PLAN_ID": SLUG})
        self.assertIn('"decision":"block"', self._gate())

    def test_no_root_mode_leaves_a_slug_plan_exactly_as_before(self):
        """The legacy invariant: projects without a root .mode see no change."""
        out = self._inject()
        self.assertIn("BEGIN-PWF-DATA", out)
        self.assertNotIn("requires attested plan", out)

    def test_no_root_mode_still_lets_a_slug_turn_the_guard_off(self):
        (self.slug_dir / ".mode").write_text(
            "autonomous plan-guard-off\n", encoding="utf-8"
        )
        self.assertNotIn("PLAN REGRESSED", self._regress_the_plan())

    def test_the_guard_fires_on_this_fixture_without_any_mode_file(self):
        """Positive control for the three tests above: the fixture really does
        trip the guard, so a NotIn assertion is evidence of the token working
        rather than of a fixture that never regressed anything."""
        self.assertIn("PLAN REGRESSED", self._regress_the_plan())

    def test_init_session_seeds_a_new_slug_from_the_root_mode(self):
        """inject-plan.sh enforces the floor at read time, so this is not the
        guard. It makes the effective policy visible in the plan directory and
        gives the new plan the nonce and attestation autonomous mode needs."""
        (self.root / ".mode").write_text("autonomous\n", encoding="utf-8")
        result = self._run("init-session.sh", "arbitrary task")
        self.assertEqual(0, result.returncode, result.stderr)
        created = [
            d for d in (self.root / ".planning").iterdir()
            if d.is_dir() and d.name != SLUG
        ]
        self.assertEqual(1, len(created), created)
        new_slug = created[0]
        self.assertIn("autonomous", (new_slug / ".mode").read_text(encoding="utf-8"))
        self.assertTrue((new_slug / ".attestation").exists())

    def test_init_session_without_a_root_mode_writes_no_mode(self):
        result = self._run("init-session.sh", "arbitrary task")
        self.assertEqual(0, result.returncode, result.stderr)
        created = [
            d for d in (self.root / ".planning").iterdir()
            if d.is_dir() and d.name != SLUG
        ]
        self.assertEqual(1, len(created), created)
        self.assertFalse((created[0] / ".mode").exists())


if __name__ == "__main__":
    unittest.main()
