"""Tests for scripts/check-complete.sh resolver integration (v2.40).

Before v2.40, check-complete.sh defaulted to `./task_plan.md` when invoked
without arguments. Any caller running in pure-slug-mode (no root plan, only
`.planning/<slug>/task_plan.md` + `.active_plan`) would receive the
"No task_plan.md found" message even though an active plan existed.

The Stop hook in SKILL.md frontmatter passes the resolved plan path
explicitly, so this was silent: only user-driven invocations or third-party
tooling that called check-complete with no args hit the bug.

v2.40 wires check-complete.sh into resolve-plan-dir.sh when no explicit path is
passed, restoring slug-mode parity.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECK_COMPLETE = REPO_ROOT / "scripts" / "check-complete.sh"
CANONICAL_TEMPLATES = REPO_ROOT / "skills" / "planning-with-files" / "templates"
ROOT_TEMPLATES = REPO_ROOT / "templates"

# Both canonical plan templates ship 5 phases: Phase 1 in_progress, 2-5 pending.
TEMPLATE_NAMES = ("task_plan.md", "task_plan_autonomous.md")


PLAN_WITH_FIVE_PHASES = """# Task Plan: Smoke

## Phases

### Phase 1
- **Status:** in_progress

### Phase 2
- **Status:** pending

### Phase 3
- **Status:** pending

### Phase 4
- **Status:** pending

### Phase 5
- **Status:** pending
"""

PLAN_ALL_COMPLETE = """# Task Plan: Done

## Phases

### Phase 1
- **Status:** complete

### Phase 2
- **Status:** complete
"""


class CheckCompleteResolverTests(unittest.TestCase):
    def run_check(self, cwd: Path, plan_id: str | None = None, arg: str | None = None) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.pop("PLAN_ID", None)
        if plan_id is not None:
            env["PLAN_ID"] = plan_id
        cmd = ["sh", str(CHECK_COMPLETE)]
        if arg is not None:
            cmd.append(arg)
        return subprocess.run(
            cmd,
            cwd=str(cwd),
            text=True,
            encoding="utf-8",
            capture_output=True,
            env=env,
            check=False,
        )

    def test_explicit_path_arg_still_works(self) -> None:
        # Backward compat: passing the plan-file path directly bypasses the
        # resolver and operates on that file. The Stop hook in SKILL.md does
        # this; the contract must not change.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "task_plan.md").write_text(PLAN_WITH_FIVE_PHASES, encoding="utf-8")
            result = self.run_check(root, arg="task_plan.md")
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("0/5 phases complete", result.stdout)

    def test_no_args_resolves_slug_plan_via_active_pointer(self) -> None:
        # Regression for v2.40: with only .planning/<slug>/task_plan.md and an
        # .active_plan pointer, no-args invocation must resolve the slug plan
        # instead of falling back to "no task_plan.md".
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_dir = root / ".planning" / "2026-05-21-smoke"
            plan_dir.mkdir(parents=True)
            (plan_dir / "task_plan.md").write_text(PLAN_WITH_FIVE_PHASES, encoding="utf-8")
            (root / ".planning" / ".active_plan").write_text("2026-05-21-smoke\n", encoding="utf-8")
            result = self.run_check(root)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("0/5 phases complete", result.stdout)
            self.assertNotIn("No task_plan.md found", result.stdout)

    def test_no_args_resolves_via_plan_id_env(self) -> None:
        # PLAN_ID env takes precedence over .active_plan in the resolver. The
        # check-complete script should honor that exact chain.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            alpha = root / ".planning" / "alpha"
            beta = root / ".planning" / "beta"
            alpha.mkdir(parents=True)
            beta.mkdir(parents=True)
            (alpha / "task_plan.md").write_text(PLAN_ALL_COMPLETE, encoding="utf-8")
            (beta / "task_plan.md").write_text(PLAN_WITH_FIVE_PHASES, encoding="utf-8")
            (root / ".planning" / ".active_plan").write_text("beta\n", encoding="utf-8")
            # PLAN_ID env should override .active_plan, pointing at alpha (all complete).
            result = self.run_check(root, plan_id="alpha")
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("ALL PHASES COMPLETE", result.stdout)

    def test_no_args_legacy_root_plan_still_works(self) -> None:
        # Backward compat: when no slug-mode plans exist but a root-level
        # task_plan.md does, the resolver returns empty and we fall back to the
        # legacy root path. v1.x users keep working.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "task_plan.md").write_text(PLAN_WITH_FIVE_PHASES, encoding="utf-8")
            result = self.run_check(root)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("0/5 phases complete", result.stdout)

    def test_no_args_no_plan_anywhere_clean_message(self) -> None:
        # If no plan exists in either location, the script must say so and exit
        # 0 (Stop hook contract).
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = self.run_check(root)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("No task_plan.md found", result.stdout)


class TemplateNextStepTests(unittest.TestCase):
    """v3.8.0: plan templates gain a '## Next Step' section right after '## Goal'.

    check-complete.sh derives phase totals from '### Phase' headings, status
    counts from '**Status:** ...' lines, and the gate's in_progress phase name
    from the first '### ' heading above an in_progress status. The new section
    is a '##' heading plus one bracketed placeholder line, so none of those
    patterns may shift. These tests run the real script against the real
    templates to pin that down.
    """

    def template_body(self, name: str) -> str:
        return (CANONICAL_TEMPLATES / name).read_text(encoding="utf-8")

    def run_check_on_template(self, name: str, root: Path, *, gate: bool = False) -> subprocess.CompletedProcess[str]:
        shutil.copyfile(CANONICAL_TEMPLATES / name, root / "task_plan.md")
        cmd = ["sh", str(CHECK_COMPLETE)]
        if gate:
            cmd.append("--gate")
        cmd.append("task_plan.md")
        return subprocess.run(
            cmd,
            cwd=str(root),
            text=True,
            encoding="utf-8",
            capture_output=True,
            input=json.dumps({"stop_hook_active": False}),
            check=False,
        )

    def test_canonical_templates_contain_next_step(self) -> None:
        for name in TEMPLATE_NAMES:
            body = self.template_body(name)
            self.assertIn("## Next Step", body, name)
            self.assertIn(
                "[The single next action. Update whenever phase status changes.]",
                body,
                name,
            )

    def test_root_template_copy_contains_next_step(self) -> None:
        # templates/task_plan.md is a manually maintained copy; sync-ide-folders
        # does not manage the repo-root templates dir. The autonomous template
        # deliberately has no root copy.
        body = (ROOT_TEMPLATES / "task_plan.md").read_text(encoding="utf-8")
        self.assertIn("## Next Step", body)

    def test_next_step_sits_between_goal_and_current_phase(self) -> None:
        # Placement contract: directly after ## Goal, so the section rides
        # inside the head-30/head-50 hook injections.
        for name in TEMPLATE_NAMES:
            body = self.template_body(name)
            goal = body.index("## Goal")
            next_step = body.index("## Next Step")
            current = body.index("## Current Phase")
            self.assertLess(goal, next_step, name)
            self.assertLess(next_step, current, name)

    def test_template_phase_counts_unchanged(self) -> None:
        # 5 phases, 0 complete, 1 in_progress, 4 pending, with the new section
        # present. A count shift here means the section leaked a parse token.
        for name in TEMPLATE_NAMES:
            with tempfile.TemporaryDirectory() as tmp:
                result = self.run_check_on_template(name, Path(tmp))
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertIn("0/5 phases complete", result.stdout, name)
                self.assertIn("1 phase(s) still in progress", result.stdout, name)
                self.assertIn("4 phase(s) pending", result.stdout, name)

    def test_gate_extracts_phase_1_as_in_progress(self) -> None:
        # in_progress extraction: the gate names the first in_progress phase in
        # its block reason. '## Next Step' is a '##' heading, so the awk pass
        # tracking '### ' headings must still land on Phase 1.
        for name in TEMPLATE_NAMES:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / ".mode").write_text("gate\n", encoding="utf-8")
                result = self.run_check_on_template(name, root, gate=True)
                self.assertEqual(0, result.returncode, result.stderr)
                decision_lines = [
                    ln for ln in result.stdout.splitlines() if ln.startswith("{")
                ]
                self.assertEqual(1, len(decision_lines), result.stdout)
                decision = json.loads(decision_lines[0])
                self.assertEqual("block", decision["decision"], name)
                self.assertIn(
                    "Phase 1: Requirements & Discovery", decision["reason"], name
                )



    def test_init_session_output_contains_next_step(self):
        """v3.8.1 regression: init-session writes plans from an inline heredoc,
        not from templates/task_plan.md, so the v3.8.0 Next Step section never
        reached created plans. Assert the OUTPUT, not the template."""
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory(prefix="pwf-nextstep-") as tmp:
            script = REPO_ROOT / "skills" / "planning-with-files" / "scripts" / "init-session.sh"
            result = subprocess.run(
                ["sh", str(script), "next-step-probe"],
                cwd=tmp, capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            created = Path(tmp) / ".planning"
            plans = list(created.glob("*/task_plan.md"))
            self.assertEqual(len(plans), 1, f"expected one plan, got {plans}")
            body = plans[0].read_text(encoding="utf-8")
            self.assertIn("## Next Step", body)
            self.assertIn("[The single next action. Update whenever phase status changes.]", body)

if __name__ == "__main__":
    unittest.main()
