"""Structure-aware injection (PWF_INJECT=smart) and SHA-cache namespacing tests.

v3.8.0 additions to inject-plan.sh:

  * Smart shape (opt-in): head-N is position-blind, so in a long plan the
    in_progress phase and the Decisions journal sit past the injected window.
    With PWF_INJECT=smart (or an "inject-smart" token in .mode) the injection
    emits title + Goal/Next Step/Current Phase + phase counts + the full first
    in_progress phase section + the last 3 Decisions rows. Default output stays
    byte-identical to v2.43 (legacy invariant, covered by test_hook_body_v240).
  * SHA cache key includes the project root: the relative "task_plan.md" key
    made every legacy-root project on a machine share one cache slot, so a
    stale hit could report a false [PLAN TAMPERED] for another project.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = REPO_ROOT / "skills" / "planning-with-files"
INJECT_PLAN = SKILL_DIR / "scripts" / "inject-plan.sh"
ATTEST_PLAN = SKILL_DIR / "scripts" / "attest-plan.sh"


def have_sh() -> bool:
    return shutil.which("sh") is not None


def run_inject(cwd: Path, context: str = "userprompt", env_extra: dict | None = None):
    env = os.environ.copy()
    env.pop("PWF_INJECT", None)
    env.pop("PLAN_ID", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["sh", str(INJECT_PLAN), f"--context={context}"],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


LATE_PLAN = """# Task Plan: long mission

## Goal
Ship the long mission without losing the active phase.

## Next Step
Write the regression test for phase 6.

## Current Phase
Phase 6

## Phases

### Phase 1: Discovery
""" + "\n".join(f"- [x] discovery item {i}" for i in range(1, 12)) + """
- **Status:** complete

### Phase 2: Design
""" + "\n".join(f"- [x] design item {i}" for i in range(1, 12)) + """
- **Status:** complete

### Phase 3: Build A
""" + "\n".join(f"- [x] build item {i}" for i in range(1, 12)) + """
- **Status:** complete

### Phase 4: Build B
""" + "\n".join(f"- [x] more item {i}" for i in range(1, 12)) + """
- **Status:** complete

### Phase 5: Integrate
- [x] integrated
- **Status:** complete

### Phase 6: Verify
- [ ] write the regression test
- [ ] run the suite
- **Status:** in_progress

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| d1 | r1 |
| d2 | r2 |
| d3 | r3 |
| d4 | r4 |
| d5 | r5 |

## Errors Encountered
| Error | Resolution |
|-------|------------|
"""


@unittest.skipUnless(have_sh(), "requires a POSIX sh")
class SmartInjectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pwf-smart-"))
        (self.tmp / "task_plan.md").write_text(LATE_PLAN, encoding="utf-8")
        (self.tmp / "progress.md").write_text("## Log\n- started\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_default_head50_misses_active_phase(self) -> None:
        # Documents the problem smart mode solves: the in_progress phase sits
        # past line 50 of this plan and default injection never carries it.
        result = run_inject(self.tmp)
        self.assertEqual(result.returncode, 0)
        self.assertIn("===BEGIN-PWF-DATA kind=plan nonce=", result.stdout)
        self.assertNotIn("### Phase 6: Verify", result.stdout)

    def test_smart_carries_active_phase_and_structure(self) -> None:
        result = run_inject(self.tmp, env_extra={"PWF_INJECT": "smart"})
        self.assertEqual(result.returncode, 0)
        out = result.stdout
        self.assertIn("# Task Plan: long mission", out)
        self.assertIn("## Goal", out)
        self.assertIn("## Next Step", out)
        self.assertIn("phases: 5/6 complete", out)
        self.assertIn("### Phase 6: Verify", out)
        self.assertIn("- [ ] write the regression test", out)
        # Completed-phase bodies must NOT be re-injected.
        self.assertNotIn("discovery item 1", out)
        # Last 3 decisions only.
        self.assertIn("| d3 | r3 |", out)
        self.assertIn("| d5 | r5 |", out)
        self.assertNotIn("| d1 | r1 |", out)
        # Canonical data-only frame remains intact around the selected bytes.
        self.assertIn("===BEGIN-PWF-DATA kind=plan nonce=", out)
        self.assertIn("===END-PWF-DATA kind=plan nonce=", out)

    def test_smart_is_smaller_than_head50_on_late_plan(self) -> None:
        default = run_inject(self.tmp).stdout
        smart = run_inject(self.tmp, env_extra={"PWF_INJECT": "smart"}).stdout
        self.assertLess(len(smart), len(default))

    def test_smart_applies_to_pretool_context(self) -> None:
        result = run_inject(
            self.tmp, context="pretool", env_extra={"PWF_INJECT": "smart"}
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("### Phase 6: Verify", result.stdout)

    def test_smart_mode_token_in_mode_file(self) -> None:
        (self.tmp / ".mode").write_text("inject-smart\n", encoding="utf-8")
        result = run_inject(self.tmp)
        self.assertEqual(result.returncode, 0)
        self.assertIn("### Phase 6: Verify", result.stdout)
        # inject-smart alone is not a v3 mode: no attestation requirement.
        self.assertNotIn("requires attested plan", result.stdout)

    def test_headingless_plan_falls_back_to_head(self) -> None:
        (self.tmp / "task_plan.md").write_text(
            "# Notes\n\nfreeform planning text\nno phase headings here\n",
            encoding="utf-8",
        )
        default = run_inject(self.tmp).stdout
        smart = run_inject(self.tmp, env_extra={"PWF_INJECT": "smart"}).stdout
        self.assertEqual(default, smart)
        self.assertIn("freeform planning text", smart)

    def test_default_output_unchanged_without_optin(self) -> None:
        # The legacy invariant: no env, no mode token, default output carries
        # the plain head-50 (phase 1 body present, phase 6 absent).
        result = run_inject(self.tmp)
        self.assertIn("discovery item 1", result.stdout)
        self.assertNotIn("phases: 5/6 complete", result.stdout)


@unittest.skipUnless(have_sh(), "requires a POSIX sh")
class ExactSnapshotAttestationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pwf-shakey-"))
        self.cache = self.tmp / "cache"
        self.proj_a = self.tmp / "proj_a"
        self.proj_b = self.tmp / "proj_b"
        for proj, body in ((self.proj_a, "plan A"), (self.proj_b, "plan B")):
            proj.mkdir(parents=True)
            (proj / "task_plan.md").write_text(
                f"# Task Plan: {body}\n\n### Phase 1: Work\n- **Status:** in_progress\n",
                encoding="utf-8",
            )
            (proj / "progress.md").write_text("- log\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _attest(self, proj: Path) -> None:
        env = os.environ.copy()
        env["XDG_CACHE_HOME"] = str(self.cache)
        result = subprocess.run(
            ["sh", str(ATTEST_PLAN)],
            cwd=str(proj),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_two_projects_are_verified_without_a_digest_cache(self) -> None:
        self._attest(self.proj_a)
        self._attest(self.proj_b)
        # Identical mtimes must never become an attestation trust decision.
        mtime = os.stat(self.proj_a / "task_plan.md").st_mtime
        os.utime(self.proj_a / "task_plan.md", (mtime, mtime))
        os.utime(self.proj_b / "task_plan.md", (mtime, mtime))

        env = {"XDG_CACHE_HOME": str(self.cache)}
        out_a = run_inject(self.proj_a, env_extra=env).stdout
        out_b = run_inject(self.proj_b, env_extra=env).stdout
        self.assertIn("===BEGIN-PWF-DATA kind=plan nonce=", out_a)
        self.assertNotIn("TAMPERED", out_a)
        self.assertIn(
            "===BEGIN-PWF-DATA kind=plan nonce=",
            out_b,
            f"project B failed independent snapshot verification: {out_b!r}",
        )
        self.assertNotIn("TAMPERED", out_b)
        self.assertFalse((self.cache / "pwf-sha").exists())


if __name__ == "__main__":
    unittest.main()
