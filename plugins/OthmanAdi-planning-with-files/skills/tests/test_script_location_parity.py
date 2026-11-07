"""Location parity for dual-shipped scripts (root scripts/ vs skill scripts/).

The hook dispatchers resolve scripts from three locations: the skill install dir
(``${CLAUDE_SKILL_DIR}/scripts``), the bare-skill known path
(``~/.claude/skills/planning-with-files/scripts``), and the plugin-marketplace
fallback (``~/.claude/plugins/marketplaces/planning-with-files/scripts``). The
marketplace path is the REPO ROOT ``scripts/`` directory, so every script the
dispatchers call — directly or as a sibling (inject-plan.sh shells
``${SCRIPT_DIR}/ledger-summary.sh``) — must exist in BOTH locations with
identical content.

This was a live bug before this test existed: the v3 review wave restored
inject-plan.sh and gate-stop.sh to root scripts/ but not the ledger trio, so the
marketplace route in autonomous/gated mode silently fell back to injecting the
raw progress.md tail — the exact surface the structured ledger summary is
documented to close (SKILL.md "Structured ledger injection").
"""
from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ROOT_SCRIPTS = REPO_ROOT / "scripts"
SKILL_SCRIPTS = REPO_ROOT / "skills" / "planning-with-files" / "scripts"

# Every script the hook dispatchers reach from a scripts/ directory, in both
# shell and PowerShell forms. Sibling dependencies count: inject-plan.sh calls
# ledger-summary.sh, gate-stop.sh calls check-complete.sh, init-session calls
# attest-plan and resolve-plan-dir, ledger-summary/phase-status back the
# autonomous-mode injection and the gate's phase reporting.
DUAL_SHIPPED = [
    "attest-plan.ps1",
    "attest-plan.sh",
    "check-complete.ps1",
    "check-complete.sh",
    "gate-stop.sh",
    "init-session.ps1",
    "init-session.sh",
    "inject-plan.sh",
    "inject-plan.py",
    "skill-hook.sh",
    "ledger-append.ps1",
    "ledger-append.sh",
    "ledger-summary.ps1",
    "ledger-summary.sh",
    "phase-status.ps1",
    "phase-status.sh",
    "plan-doctor.sh",
    "resolve-plan-dir.ps1",
    "resolve-plan-dir.sh",
    "set-active-plan.ps1",
    "set-active-plan.sh",
]


class ScriptLocationParityTests(unittest.TestCase):
    def test_dual_shipped_scripts_exist_in_both_locations(self) -> None:
        for name in DUAL_SHIPPED:
            with self.subTest(script=name):
                self.assertTrue(
                    (ROOT_SCRIPTS / name).is_file(),
                    f"scripts/{name} missing — plugin-marketplace fallback route breaks",
                )
                self.assertTrue(
                    (SKILL_SCRIPTS / name).is_file(),
                    f"skills/planning-with-files/scripts/{name} missing — skill install route breaks",
                )

    def test_dual_shipped_scripts_are_byte_identical(self) -> None:
        for name in DUAL_SHIPPED:
            root_file = ROOT_SCRIPTS / name
            skill_file = SKILL_SCRIPTS / name
            if not (root_file.is_file() and skill_file.is_file()):
                continue  # existence failures are reported by the test above
            with self.subTest(script=name):
                self.assertEqual(
                    root_file.read_bytes(),
                    skill_file.read_bytes(),
                    f"{name} drifted between scripts/ and skill scripts/ — "
                    "the two install routes would behave differently",
                )


if __name__ == "__main__":
    unittest.main()
