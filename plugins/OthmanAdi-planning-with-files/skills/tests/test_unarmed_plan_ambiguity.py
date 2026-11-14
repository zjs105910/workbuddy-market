"""Issue #240: shared pointers and mtimes never bind multiple named plans."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
NOTICE = "Set PLAN_ID=<slug>"
TOKEN = "PWF_PLAN_AMBIGUOUS_V1"


@unittest.skipUnless(shutil.which("sh"), "requires POSIX sh")
class UnarmedPlanAmbiguityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pwf-unarmed-")
        self.root = Path(self.temp.name)
        self.env = os.environ.copy()
        for key in ("PLAN_ID", "PWF_PLAN_ROOT", "PWF_SESSION_ID", "PWF_SESSION_KEY", "PLANNING_DISABLED"):
            self.env.pop(key, None)
        self.env.update(PWF_TRUSTED_PYTHON=sys.executable, PYTHON_BIN=sys.executable,
                        XDG_CACHE_HOME=str(self.root / "cache"))

    def tearDown(self):
        self.temp.cleanup()

    def plan(self, name):
        directory = self.root / ".planning" / name
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "task_plan.md").write_text("# NAMED-" + name + "\n", encoding="utf-8")
        return directory

    def two_plans(self, *, legacy=False):
        self.plan("alpha")
        self.plan("beta")
        if legacy:
            (self.root / "task_plan.md").write_text(
                "# LEGACY-ROOT\n\n### Phase 1\n- **Status:** complete\n", encoding="utf-8"
            )

    def run_script(self, name, *args, extra=None):
        env = dict(self.env)
        env.update(extra or {})
        if name.endswith(".py"):
            prefix = [sys.executable, "-I"]
        elif name.endswith(".ps1"):
            executable = shutil.which("pwsh") or shutil.which("powershell")
            if not executable:
                self.skipTest("requires PowerShell")
            prefix = [executable, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File"]
        else:
            prefix = ["sh"]
        return subprocess.run(
            prefix + [str(SCRIPTS / name), *args], cwd=self.root,
            env=env, capture_output=True, text=True, encoding="utf-8", timeout=90,
        )

    def test_shared_resolvers_refuse_pointer_and_mtime_with_diagnostic_probe(self):
        self.two_plans()
        pointer = self.root / ".planning" / ".active_plan"
        for selected in (None, "alpha", "beta"):
            if selected:
                pointer.write_text(selected + "\n", encoding="utf-8")
            for script, probe in (("resolve-plan-dir.sh", "--check-ambiguity"),
                                  ("resolve-plan-dir.ps1", "-CheckAmbiguity")):
                with self.subTest(pointer=selected, script=script):
                    result = self.run_script(script)
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertEqual("", result.stdout.strip())
                    diagnostic = self.run_script(script, probe)
                    self.assertEqual(0, diagnostic.returncode, diagnostic.stderr)
                    self.assertEqual(TOKEN, diagnostic.stdout.strip())

    def test_both_injectors_refuse_all_unbound_contexts_without_exposing_plan(self):
        self.two_plans(legacy=True)
        (self.root / ".planning" / ".active_plan").write_text("alpha\n", encoding="utf-8")
        for context in ("userprompt", "pretool", "precompact", "preflight", "validate"):
            outputs = []
            for script in ("inject-plan.sh", "inject-plan.py"):
                result = self.run_script(script, "--context=" + context)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertNotIn("NAMED-", result.stdout)
                self.assertNotIn("LEGACY-ROOT", result.stdout)
                if context == "userprompt":
                    self.assertEqual(1, result.stdout.count(NOTICE))
                else:
                    self.assertEqual("", result.stdout)
                outputs.append(result.stdout)
            self.assertEqual(outputs[0], outputs[1])

    def test_explicit_plan_binding_works_and_root_pin_alone_is_insufficient(self):
        self.two_plans()
        for script, probe in (("resolve-plan-dir.sh", "--check-ambiguity"),
                              ("resolve-plan-dir.ps1", "-CheckAmbiguity")):
            pinned = self.run_script(script, extra={"PLAN_ID": "alpha"})
            self.assertEqual(0, pinned.returncode, pinned.stderr)
            self.assertTrue(pinned.stdout.strip().endswith("alpha"), pinned.stdout)
            self.assertEqual("", self.run_script(script, probe, extra={"PLAN_ID": "alpha"}).stdout)
            root_only = self.run_script(script, probe, extra={"PWF_PLAN_ROOT": str(self.root)})
            self.assertEqual(TOKEN, root_only.stdout.strip())
        for script in ("inject-plan.sh", "inject-plan.py"):
            accepted = self.run_script(script, "--context=validate", extra={"PLAN_ID": "beta"})
            self.assertEqual("PWF_PLAN_ACCEPTED_V1", accepted.stdout.strip(), accepted.stderr)

    def link_plan(self, name, target):
        """Link .planning/<name> at *target* (junction on Windows, symlink elsewhere) or skip."""
        link = self.root / ".planning" / name
        if os.name == "nt":
            made = subprocess.run(["cmd", "/d", "/c", "mklink", "/J", str(link), str(target)],
                                  capture_output=True, text=True, check=False)
            if made.returncode != 0:
                self.skipTest("junction creation unavailable: " + made.stderr.strip())
        else:
            try:
                link.symlink_to(target, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"symlink creation unavailable: {exc}")
        return link

    def test_linked_plan_directory_never_counts_on_any_route(self):
        # #270: a symlinked or junctioned plan directory is not selectable, so no
        # counter treats it as a second plan; the real plan resolves as before.
        self.plan("alpha")
        target = self.root / "linked-target"
        target.mkdir()
        (target / "task_plan.md").write_text("# NAMED-linked\n", encoding="utf-8")
        self.link_plan("beta", target)
        for script, probe in (("resolve-plan-dir.sh", "--check-ambiguity"),
                              ("resolve-plan-dir.ps1", "-CheckAmbiguity")):
            with self.subTest(script=script):
                resolved = self.run_script(script)
                self.assertEqual(0, resolved.returncode, resolved.stderr)
                self.assertTrue(resolved.stdout.strip().endswith("alpha"), resolved.stdout)
                self.assertEqual("", self.run_script(script, probe).stdout.strip())
        for script in ("inject-plan.sh", "inject-plan.py"):
            with self.subTest(script=script):
                result = self.run_script(script, "--context=userprompt")
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertIn("NAMED-alpha", result.stdout)
                self.assertNotIn(NOTICE, result.stdout)
        # PLAN_ID naming the link fails closed on every route; the pointer naming
        # it falls through to the real plan like a stale pointer does
        for script, probe in (("resolve-plan-dir.sh", "--check-ambiguity"),
                              ("resolve-plan-dir.ps1", "-CheckAmbiguity")):
            with self.subTest(script=script, selector="PLAN_ID at link"):
                self.assertEqual("", self.run_script(script, extra={"PLAN_ID": "beta"}).stdout.strip())
        for script in ("inject-plan.sh", "inject-plan.py"):
            with self.subTest(script=script, selector="PLAN_ID at link"):
                result = self.run_script(script, "--context=userprompt", extra={"PLAN_ID": "beta"})
                self.assertIn("PLAN_ID does not name a plan directory", result.stdout)
                self.assertNotIn("NAMED-", result.stdout)
        (self.root / ".planning" / ".active_plan").write_text("beta\n", encoding="utf-8")
        for script, probe in (("resolve-plan-dir.sh", "--check-ambiguity"),
                              ("resolve-plan-dir.ps1", "-CheckAmbiguity")):
            with self.subTest(script=script, selector="pointer at link"):
                self.assertTrue(self.run_script(script).stdout.strip().endswith("alpha"))
        for script in ("inject-plan.sh", "inject-plan.py"):
            with self.subTest(script=script, selector="pointer at link"):
                result = self.run_script(script, "--context=userprompt")
                self.assertIn("NAMED-alpha", result.stdout)
                self.assertNotIn("NAMED-linked", result.stdout)
        (self.root / ".planning" / ".active_plan").unlink()
        # a second real plan still requires the selector everywhere
        self.plan("gamma")
        for script, probe in (("resolve-plan-dir.sh", "--check-ambiguity"),
                              ("resolve-plan-dir.ps1", "-CheckAmbiguity")):
            with self.subTest(script=script, plans="two real"):
                self.assertEqual(TOKEN, self.run_script(script, probe).stdout.strip())
        for script in ("inject-plan.sh", "inject-plan.py"):
            with self.subTest(script=script, plans="two real"):
                self.assertIn(NOTICE, self.run_script(script, "--context=userprompt").stdout)

    def test_single_named_plan_with_legacy_root_is_compatible_until_isolation_armed(self):
        self.plan("alpha")
        (self.root / "task_plan.md").write_text("# LEGACY-ROOT\n", encoding="utf-8")
        for script, probe in (("resolve-plan-dir.sh", "--check-ambiguity"),
                              ("resolve-plan-dir.ps1", "-CheckAmbiguity")):
            self.assertTrue(self.run_script(script).stdout.strip().endswith("alpha"))
            self.assertEqual("", self.run_script(script, probe).stdout)
        (self.root / ".planning" / "sessions").mkdir()
        for script, probe in (("resolve-plan-dir.sh", "--check-ambiguity"),
                              ("resolve-plan-dir.ps1", "-CheckAmbiguity")):
            self.assertEqual("", self.run_script(script).stdout)
            self.assertEqual(TOKEN, self.run_script(script, probe).stdout.strip())

    def test_ambiguous_completion_and_attestation_do_not_fall_back_to_root(self):
        self.two_plans(legacy=True)
        for suffix in ("sh", "ps1"):
            if suffix == "ps1" and os.name != "nt":
                continue  # PowerShell attestation deliberately supports Windows only.
            completion = self.run_script("check-complete." + suffix)
            self.assertEqual(0, completion.returncode, completion.stderr)
            self.assertEqual("", completion.stdout.strip())
            attested = self.run_script("attest-plan." + suffix)
            self.assertNotEqual(0, attested.returncode)
            if suffix == "sh":
                self.assertIn("PLAN_ID", attested.stdout + attested.stderr)
            self.assertFalse((self.root / ".plan-attestation").exists())
            self.assertFalse(list((self.root / ".planning").glob("*/.attestation")))

    def test_python_dispatcher_does_not_fall_back_to_root_for_other_events(self):
        self.two_plans(legacy=True)
        for event in ("session-start", "post-tool-use", "pre-tool-use", "pre-compact"):
            result = self.run_script("inject-plan.py", "--claude-event=" + event)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("", result.stdout)
