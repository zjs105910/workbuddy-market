"""Regression tests for the parallel-write guard (v3.10.0, issue #217).

Two sessions sharing one plan directory can both write task_plan.md from the
same read; the later write silently discards the earlier one's work. The guard
in inject-plan.sh compares PROGRESS between hook fires (checked boxes and
completed phases) rather than a raw hash, because a raw-hash comparison would
flag a single agent's own edit on its very next fire.

Verifies:
  - Forward progress emits no warning.
  - A regression (work present on the previous fire is gone) emits one warning
    naming how much was lost.
  - The warning does not repeat once the new state has been observed.
  - PWF_PLAN_GUARD=0 and a "plan-guard-off" .mode token restore the old silence.
  - The guard never fires in pretool context and never changes the exit code.

Skipped on platforms without sh in PATH (the hook is POSIX shell).
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "inject-plan.sh"
MARKER = "PLAN REGRESSED"

PLAN_TWO_DONE = """# Task Plan: Add auth API
## Phases
### Phase 1: Research
- [x] Read existing middleware
- **Status:** complete
### Phase 2: Planning
- [x] Define approach
- **Status:** complete
"""

PLAN_ONE_DONE = """# Task Plan: Add auth API
## Phases
### Phase 1: Research
- [x] Read existing middleware
- **Status:** complete
### Phase 2: Planning
- [ ] Define approach
- **Status:** in_progress
"""

PLAN_CLOBBERED = """# Task Plan: [Brief Description]
## Phases
### Phase 1: Research
- [ ] Read existing middleware
- **Status:** pending
"""


def have_sh() -> bool:
    return shutil.which("sh") is not None


@unittest.skipUnless(have_sh(), "sh not available on this platform")
class PlanRegressionGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="pwf-guard-"))
        self.scripts_dir = self.tmp / "scripts"
        self.scripts_dir.mkdir()
        shutil.copy2(SCRIPT, self.scripts_dir / "inject-plan.sh")
        self.plan = self.tmp / "task_plan.md"
        # A private HOME keeps the progress marker inside the temp dir, so these
        # tests never read or write the developer's real cache directory.
        self.home = self.tmp / "home"
        self.home.mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fire(self, context: str = "userprompt", **extra_env: str) -> str:
        env = {
            "HOME": str(self.home),
            "PATH": __import__("os").environ.get("PATH", ""),
        }
        env.update(extra_env)
        proc = subprocess.run(
            ["sh", str(self.scripts_dir / "inject-plan.sh"), f"--context={context}"],
            cwd=self.tmp,
            env=env,
            capture_output=True,
            text=True,
        )
        # The hook contracts to never break the agent loop.
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout

    def test_forward_progress_is_silent(self) -> None:
        self.plan.write_text(PLAN_ONE_DONE, encoding="utf-8")
        self.fire()
        self.plan.write_text(PLAN_TWO_DONE, encoding="utf-8")
        self.assertNotIn(MARKER, self.fire())

    def test_first_fire_is_silent(self) -> None:
        """No prior observation means nothing to compare against."""
        self.plan.write_text(PLAN_CLOBBERED, encoding="utf-8")
        self.assertNotIn(MARKER, self.fire())

    def test_regression_warns_once_with_counts(self) -> None:
        self.plan.write_text(PLAN_TWO_DONE, encoding="utf-8")
        self.fire()
        self.plan.write_text(PLAN_CLOBBERED, encoding="utf-8")
        warned = self.fire()
        self.assertIn(MARKER, warned)
        self.assertIn("lost 2 checked item(s)", warned)
        self.assertIn("2 completed phase(s)", warned)
        # The plan is still injected: the guard is advisory, not a block.
        self.assertIn("===BEGIN-PWF-DATA kind=plan nonce=", warned)
        # Second fire against the same content has nothing new to report.
        self.assertNotIn(MARKER, self.fire())

    def test_env_off_switch(self) -> None:
        self.plan.write_text(PLAN_TWO_DONE, encoding="utf-8")
        self.fire(PWF_PLAN_GUARD="0")
        self.plan.write_text(PLAN_CLOBBERED, encoding="utf-8")
        self.assertNotIn(MARKER, self.fire(PWF_PLAN_GUARD="0"))

    def test_mode_token_off_switch(self) -> None:
        (self.tmp / ".mode").write_text("plan-guard-off\n", encoding="utf-8")
        self.plan.write_text(PLAN_TWO_DONE, encoding="utf-8")
        self.fire()
        self.plan.write_text(PLAN_CLOBBERED, encoding="utf-8")
        self.assertNotIn(MARKER, self.fire())

    def test_pretool_never_warns(self) -> None:
        self.plan.write_text(PLAN_TWO_DONE, encoding="utf-8")
        self.fire()
        self.plan.write_text(PLAN_CLOBBERED, encoding="utf-8")
        self.assertNotIn(MARKER, self.fire(context="pretool"))


if __name__ == "__main__":
    unittest.main()
