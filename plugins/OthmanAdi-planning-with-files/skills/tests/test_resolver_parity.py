"""resolve-plan-dir.sh vs resolve-plan-dir.ps1 parity (v3.8.0).

The ps1 mirror lagged the sh resolver: no slug validation on any branch, no
task_plan.md requirement in the newest-dir scan (a sessions/ dir could win),
and containment failed OPEN on canonicalization failure. These tests run both
resolvers over the same fixture trees and assert identical resolution. pwsh
ships on both ubuntu and windows CI runners, so the parity holds on both legs.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SH_RESOLVER = REPO_ROOT / "skills" / "planning-with-files" / "scripts" / "resolve-plan-dir.sh"
PS1_RESOLVER = REPO_ROOT / "skills" / "planning-with-files" / "scripts" / "resolve-plan-dir.ps1"


def pwsh_exe() -> str | None:
    return shutil.which("pwsh") or shutil.which("powershell")


def have_sh() -> bool:
    return shutil.which("sh") is not None


def run_sh(cwd: Path, env_extra: dict | None = None) -> str:
    env = os.environ.copy()
    env.pop("PLAN_ID", None)
    if env_extra:
        env.update(env_extra)
    result = subprocess.run(
        ["sh", str(SH_RESOLVER)],
        cwd=str(cwd), env=env, capture_output=True, text=True, timeout=60,
    )
    return result.stdout.strip()


def run_ps1(cwd: Path, env_extra: dict | None = None) -> str:
    env = os.environ.copy()
    env.pop("PLAN_ID", None)
    if env_extra:
        env.update(env_extra)
    exe = pwsh_exe()
    assert exe is not None
    result = subprocess.run(
        [exe, "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(PS1_RESOLVER)],
        cwd=str(cwd), env=env, capture_output=True, text=True, timeout=120,
    )
    return result.stdout.strip()


def canon(cwd: Path, out: str) -> str | None:
    """Both resolvers may emit relative or absolute paths; compare resolved.

    On Windows the sh resolver emits Git Bash POSIX spellings (/tmp/...,
    /c/...); cygpath translates them to the Windows form before comparison.
    """
    if not out:
        return None
    if os.name == "nt" and out.startswith("/"):
        cygpath = shutil.which("cygpath")
        if cygpath:
            translated = subprocess.run(
                [cygpath, "-w", out], capture_output=True, text=True, timeout=30
            ).stdout.strip()
            if translated:
                out = translated
    p = Path(out)
    if not p.is_absolute():
        p = cwd / p
    try:
        return str(p.resolve()).lower()
    except OSError:
        return str(p).lower()


@unittest.skipUnless(have_sh(), "requires a POSIX sh")
@unittest.skipUnless(pwsh_exe(), "requires PowerShell")
class ResolverParityTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tempdir = tempfile.TemporaryDirectory(prefix="pwf-parity-")
        self.tmp = Path(self.tempdir.name)

    def tearDown(self):
        self.tempdir.cleanup()

    def _plan(self, slug: str, mtime_offset: int = 0) -> Path:
        d = self.tmp / ".planning" / slug
        d.mkdir(parents=True, exist_ok=True)
        (d / "task_plan.md").write_text("# plan\n", encoding="utf-8")
        if mtime_offset:
            t = time.time() + mtime_offset
            os.utime(d, (t, t))
        return d

    def assert_parity(self, env_extra: dict | None = None, expect_slug: str | None = None):
        sh_out = canon(self.tmp, run_sh(self.tmp, env_extra))
        ps_out = canon(self.tmp, run_ps1(self.tmp, env_extra))
        self.assertEqual(sh_out, ps_out, "sh and ps1 resolved differently")
        if expect_slug is None:
            self.assertIsNone(sh_out)
        else:
            assert sh_out is not None, "resolver returned nothing"
            self.assertTrue(
                sh_out.endswith(expect_slug.lower()),
                f"expected {expect_slug}, got {sh_out}",
            )

    def test_plan_id_env_valid(self):
        self._plan("2026-07-21-alpha")
        self._plan("2026-07-21-beta", mtime_offset=60)
        self.assert_parity({"PLAN_ID": "2026-07-21-alpha"}, "2026-07-21-alpha")

    def test_plan_id_env_traversal_slug_fails_closed(self):
        """A traversal-shaped PLAN_ID resolves to nothing, not to another plan.

        This asserted a fall-through to the newest plan until issue #237. Not
        escaping .planning was always right, but continuing to .active_plan and
        newest-by-mtime afterwards is the same wrong-plan harm as a typo: the
        operator named one plan, attest-plan.sh locked a different one at rc=0,
        and injection followed it. A set PLAN_ID is a binding for every
        rejection reason, so both resolvers now emit nothing.
        """
        self._plan("2026-07-21-alpha")
        evil = self.tmp / ".planning" / ".." / "outside"
        evil.mkdir(parents=True, exist_ok=True)
        self.assert_parity({"PLAN_ID": "../outside"}, None)

    def test_plan_id_env_valid_shape_nonexistent_fails_closed(self):
        """A one-character typo must not silently select the pointed plan.

        The core of issue #237: PLAN_ID has valid slug shape but names no
        directory, and .active_plan points at a real, different plan. The
        rejected selector must stop resolution rather than hand back beta.
        """
        self._plan("2026-07-21-alpha")
        self._plan("2026-07-21-beta", mtime_offset=60)
        (self.tmp / ".planning" / ".active_plan").write_text(
            "2026-07-21-beta\n", encoding="utf-8"
        )
        # Control arm: the same fixture DOES resolve alpha when the slug is
        # spelled correctly, so the assertion below is a real refusal rather
        # than a broken probe.
        self.assert_parity({"PLAN_ID": "2026-07-21-alpha"}, "2026-07-21-alpha")
        self.assert_parity({"PLAN_ID": "2026-07-21-alhpa"}, None)

    def test_empty_plan_id_still_means_unset(self):
        """PLAN_ID="" is not a selector; resolution proceeds normally.

        init-session.sh passes PLAN_ID="${PLAN_ID:-}" into attest-plan.sh on
        the legacy path. Empty remains unset, so it cannot select between
        multiple named plans, even with a shared pointer.
        """
        self._plan("2026-07-21-alpha")
        self._plan("2026-07-21-beta", mtime_offset=60)
        (self.tmp / ".planning" / ".active_plan").write_text(
            "2026-07-21-beta\n", encoding="utf-8"
        )
        self.assert_parity({"PLAN_ID": ""}, None)

    def test_active_plan_pointer_cannot_select_between_multiple_plans(self):
        self._plan("2026-07-21-alpha", mtime_offset=60)
        self._plan("2026-07-21-beta")
        (self.tmp / ".planning" / ".active_plan").write_text(
            "2026-07-21-beta\n", encoding="utf-8"
        )
        self.assert_parity(None, None)

    def test_active_plan_invalid_slug_falls_through_to_newest(self):
        self._plan("2026-07-21-alpha", mtime_offset=60)
        (self.tmp / ".planning" / ".active_plan").write_text(
            "../../etc\n", encoding="utf-8"
        )
        self.assert_parity(None, "2026-07-21-alpha")

    def test_newest_scan_skips_dir_without_task_plan(self):
        self._plan("2026-07-21-real")
        sessions = self.tmp / ".planning" / "sessions"
        sessions.mkdir(parents=True)
        (sessions / "log.jsonl").write_text("{}\n", encoding="utf-8")
        t = time.time() + 120
        os.utime(sessions, (t, t))
        self.assert_parity(None, "2026-07-21-real")

    def test_newest_scan_skips_hidden_dirs(self):
        self._plan("2026-07-21-real")
        hidden = self.tmp / ".planning" / ".cache"
        hidden.mkdir(parents=True)
        (hidden / "task_plan.md").write_text("# not a plan\n", encoding="utf-8")
        t = time.time() + 120
        os.utime(hidden, (t, t))
        self.assert_parity(None, "2026-07-21-real")

    def test_no_planning_dir_resolves_empty(self):
        self.assert_parity(None, None)


if __name__ == "__main__":
    unittest.main()
