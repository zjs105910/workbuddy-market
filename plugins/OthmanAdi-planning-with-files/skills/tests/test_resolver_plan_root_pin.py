"""PWF_PLAN_ROOT support in resolve-plan-dir.sh / .ps1 (issue #212).

The shared resolver is what the .codex hook route (and the documented
user-facing script surface) resolves plans through, so the absolute
plan-root binding lives here too:

  * A valid pin resolves under ${PWF_PLAN_ROOT}/.planning and overrides both
    the ${PWD} default and the positional argument (highest precedence — an
    adapter passing ".planning" is spelling out the cwd default, not
    overriding a user's deliberate pin).
  * A pin that is not a directory fails CLOSED: empty stdout, exit 0. The
    resolver's stdout is a data channel, so the user-facing notice belongs
    to the injection routes, but the resolver must never hand back the
    ambiguous cwd plan the pin was escaping.
  * Unset keeps resolution byte-identical to the legacy shape (covered
    further by test_resolve_plan_dir.py and test_resolver_parity.py).

The sh and ps1 resolvers must agree; the parity class runs both over the
same trees, mirroring tests/test_resolver_parity.py.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SH_RESOLVER = REPO_ROOT / "skills" / "planning-with-files" / "scripts" / "resolve-plan-dir.sh"
PS1_RESOLVER = REPO_ROOT / "skills" / "planning-with-files" / "scripts" / "resolve-plan-dir.ps1"

SCRUB_VARS = ("PLAN_ID", "PWF_PLAN_ROOT", "PWF_SESSION_ID", "PLANNING_DISABLED")


def pwsh_exe() -> str | None:
    return shutil.which("pwsh") or shutil.which("powershell")


def have_sh() -> bool:
    return shutil.which("sh") is not None


def scrubbed_env(env_extra: dict | None = None) -> dict:
    env = os.environ.copy()
    for var in SCRUB_VARS:
        env.pop(var, None)
    if env_extra:
        env.update(env_extra)
    return env


def run_sh(cwd: Path, env_extra: dict | None = None, args: list[str] | None = None) -> str:
    result = subprocess.run(
        ["sh", str(SH_RESOLVER), *(args or [])],
        cwd=str(cwd),
        env=scrubbed_env(env_extra),
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result.stdout.strip()


def run_ps1(cwd: Path, env_extra: dict | None = None, args: list[str] | None = None) -> str:
    exe = pwsh_exe()
    assert exe is not None
    result = subprocess.run(
        [exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(PS1_RESOLVER), *(args or [])],
        cwd=str(cwd),
        env=scrubbed_env(env_extra),
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.stdout.strip()


def canon(cwd: Path, out: str) -> str | None:
    """Compare resolved paths across emitters (POSIX vs Windows spellings)."""
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


class PinTreeMixin(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="pwf-resolver-pin-"))
        self.workspace = self.tmp / "workspace"
        self.project = self.workspace / "project"
        for root, slug in ((self.workspace, "plan-a"), (self.project, "plan-b")):
            plan = root / ".planning" / slug
            plan.mkdir(parents=True)
            (plan / "task_plan.md").write_text(f"# {slug}\n", encoding="utf-8")
            (root / ".planning" / ".active_plan").write_text(f"{slug}\n", encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)


@unittest.skipUnless(have_sh(), "requires a POSIX sh")
class ShResolverPinTests(PinTreeMixin):
    def test_pin_resolves_nested_project_from_parent_cwd(self) -> None:
        out = canon(self.workspace, run_sh(self.workspace, {"PWF_PLAN_ROOT": str(self.project)}))
        assert out is not None, "pinned resolution must produce a path"
        self.assertTrue(out.endswith("plan-b"), f"expected plan-b, got {out}")

    def test_pin_overrides_positional_argument(self) -> None:
        # permission_request.py passes ".planning"; a user pin must still win.
        out = canon(
            self.workspace,
            run_sh(self.workspace, {"PWF_PLAN_ROOT": str(self.project)}, [".planning"]),
        )
        assert out is not None
        self.assertTrue(out.endswith("plan-b"), f"expected plan-b, got {out}")

    def test_broken_pin_resolves_nothing(self) -> None:
        out = run_sh(self.workspace, {"PWF_PLAN_ROOT": str(self.workspace / "missing")})
        self.assertEqual("", out, "a broken pin must fail closed to empty stdout")

    def test_plan_id_not_under_the_pin_fails_closed(self) -> None:
        # PLAN_ID=plan-a exists at the parent but NOT under the pin. Not mixing
        # roots was always the point and still holds. Since issue #237 the
        # resolver no longer falls through to the pinned .active_plan either:
        # returning plan-b for an operator who named plan-a is the wrong-plan
        # harm the binding removes, and attest-plan.sh would have locked plan-b
        # at rc=0.
        out = run_sh(self.workspace, {"PWF_PLAN_ROOT": str(self.project), "PLAN_ID": "plan-a"})
        self.assertEqual("", out.strip(), f"expected a refusal, got {out}")

    def test_plan_id_that_does_exist_under_the_pin_still_resolves(self) -> None:
        # Control arm for the refusal above: the pin plus a slug that really is
        # under it resolves normally, so the empty result is a binding refusal
        # rather than the pin breaking PLAN_ID outright.
        out = canon(
            self.workspace,
            run_sh(self.workspace, {"PWF_PLAN_ROOT": str(self.project), "PLAN_ID": "plan-b"}),
        )
        assert out is not None
        self.assertTrue(out.endswith("plan-b"), f"expected plan-b, got {out}")

    def test_unset_pin_keeps_legacy_resolution(self) -> None:
        out = canon(self.workspace, run_sh(self.workspace))
        assert out is not None
        self.assertTrue(out.endswith("plan-a"), f"expected plan-a, got {out}")


@unittest.skipUnless(have_sh(), "requires a POSIX sh")
@unittest.skipUnless(pwsh_exe(), "requires PowerShell")
class ResolverPinParityTests(PinTreeMixin):
    """sh and ps1 must agree on every pin shape (mirrors test_resolver_parity)."""

    def assert_parity(
        self,
        env_extra: dict | None,
        expect_slug: str | None,
        args: list[str] | None = None,
    ) -> None:
        sh_out = canon(self.workspace, run_sh(self.workspace, env_extra, args))
        ps_out = canon(self.workspace, run_ps1(self.workspace, env_extra, args))
        self.assertEqual(sh_out, ps_out, "sh and ps1 resolved differently")
        if expect_slug is None:
            self.assertIsNone(sh_out)
        else:
            assert sh_out is not None, "resolver returned nothing"
            self.assertTrue(
                sh_out.endswith(expect_slug.lower()),
                f"expected {expect_slug}, got {sh_out}",
            )

    def test_pin_parity(self) -> None:
        self.assert_parity({"PWF_PLAN_ROOT": str(self.project)}, "plan-b")

    def test_pin_overrides_argument_parity(self) -> None:
        self.assert_parity({"PWF_PLAN_ROOT": str(self.project)}, "plan-b", [".planning"])

    def test_broken_pin_parity(self) -> None:
        self.assert_parity({"PWF_PLAN_ROOT": str(self.workspace / "missing")}, None)

    def test_unset_pin_parity(self) -> None:
        self.assert_parity(None, "plan-a")

    def test_plan_id_outside_the_pin_fails_closed_on_both(self) -> None:
        # Issue #237: both resolvers must refuse rather than substitute the
        # pinned .active_plan. A host disagreement here would put the shell
        # route and the PowerShell route on different plans.
        self.assert_parity(
            {"PWF_PLAN_ROOT": str(self.project), "PLAN_ID": "plan-a"}, None
        )

    def test_plan_id_inside_the_pin_resolves_on_both(self) -> None:
        self.assert_parity(
            {"PWF_PLAN_ROOT": str(self.project), "PLAN_ID": "plan-b"}, "plan-b"
        )


if __name__ == "__main__":
    unittest.main()
