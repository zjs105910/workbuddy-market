"""The PostToolUse nudge reaches the model, once per turn (issue #239).

The hook emitted an instruction addressed to Claude:

    [planning-with-files] Update progress.md with what you just did. ...

as ``systemMessage``, which Claude Code delivers to the USER. So the model
never received the instruction, the person received it after every ``Write``,
``Edit`` and ``Bash`` call for the whole session, and nothing rate-limited it.
``emit_session_start`` in the same file already used the correct
``hookSpecificOutput.additionalContext`` shape for its own event, which is what
made this an oversight rather than a design choice.

Three defects, fixed together and pinned here:

  1. wrong field, so the message never reached the model,
  2. no throttle, so a constant string repeated per tool call,
  3. ``Bash`` in the matcher, so ``ls`` and ``git status`` tripped a
     "you changed something" reminder.

The Codex adapter carried the identical defect with a wider matcher, so both
routes are exercised. The throttle marker lives in the user's private cache and
is keyed on the plan path plus the session id; the key-agreement test is the
one that catches a re-arm that silently never fires.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CLAUDE_HOOK = REPO_ROOT / "hooks" / "claude-hook.sh"
CODEX_HOOKS = REPO_ROOT / ".codex" / "hooks"

NUDGE = "Update progress.md with what you just did"


def have_sh() -> bool:
    return shutil.which("sh") is not None


@unittest.skipUnless(have_sh(), "requires a POSIX sh")
class PostToolNudgeTests(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile

        self.tempdir = tempfile.TemporaryDirectory(prefix="pwf-nudge-")
        self.root = Path(self.tempdir.name)
        (self.root / "task_plan.md").write_text(
            "# Task Plan: t\n### Phase 1\n- [ ] work\n", encoding="utf-8"
        )
        (self.root / "progress.md").write_text("# Progress\n", encoding="utf-8")
        self.cache = self.root / "_cache"
        self.cache.mkdir()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _env(self, **extra: str) -> dict:
        env = os.environ.copy()
        for key in ("PLAN_ID", "PWF_PLAN_ROOT", "PLANNING_DISABLED", "PWF_SESSION_ID"):
            env.pop(key, None)
        env["XDG_CACHE_HOME"] = str(self.cache)
        env["CLAUDE_PLUGIN_ROOT"] = str(REPO_ROOT)
        env.update(extra)
        return env

    def _claude(self, event: str, **extra: str) -> str:
        return subprocess.run(
            ["sh", str(CLAUDE_HOOK), event],
            cwd=str(self.root), env=self._env(**extra),
            capture_output=True, text=True, timeout=180,
        ).stdout

    def _codex(self, script: str, **extra: str) -> str:
        return subprocess.run(
            ["sh", str(CODEX_HOOKS / script)],
            cwd=str(self.root), env=self._env(**extra),
            capture_output=True, text=True, timeout=180,
        ).stdout

    # --- defect 1: the field ------------------------------------------------

    def test_claude_nudge_goes_to_the_model_not_the_user(self):
        out = self._claude("post-tool-use")
        self.assertNotIn("systemMessage", out)
        payload = json.loads(out)
        block = payload["hookSpecificOutput"]
        self.assertEqual("PostToolUse", block["hookEventName"])
        self.assertIn(NUDGE, block["additionalContext"])

    def test_codex_nudge_goes_to_the_model_not_the_user(self):
        adapter_check = subprocess.run(
            ["python", "-c", "import ast,sys;ast.parse(open(sys.argv[1],encoding='utf-8').read())",
             str(CODEX_HOOKS / "post_tool_use.py")],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(0, adapter_check.returncode, adapter_check.stderr)
        source = (CODEX_HOOKS / "post_tool_use.py").read_text(encoding="utf-8")
        self.assertIn('"hookEventName": "PostToolUse"', source)
        self.assertIn('"additionalContext": stdout', source)
        self.assertNotIn('{"systemMessage": stdout}', source)

    # --- defect 2: the throttle ---------------------------------------------

    def test_claude_nudge_fires_once_per_turn(self):
        self.assertIn(NUDGE, self._claude("post-tool-use"))
        self.assertEqual("", self._claude("post-tool-use").strip())
        self.assertEqual("", self._claude("post-tool-use").strip())
        self._claude("user-prompt-submit")
        self.assertIn(NUDGE, self._claude("post-tool-use"))

    def test_claude_session_start_also_rearms(self):
        self.assertIn(NUDGE, self._claude("post-tool-use"))
        self.assertEqual("", self._claude("post-tool-use").strip())
        self._claude("session-start")
        self.assertIn(NUDGE, self._claude("post-tool-use"))

    def test_codex_nudge_fires_once_per_turn(self):
        self.assertIn(NUDGE, self._codex("post-tool-use.sh"))
        self.assertEqual("", self._codex("post-tool-use.sh").strip())
        self._codex("user-prompt-submit.sh")
        self.assertIn(NUDGE, self._codex("post-tool-use.sh"))

    def test_codex_rearm_and_throttle_agree_on_one_marker_slot(self):
        """The failure this catches is silent.

        post-tool-use.sh and user-prompt-submit.sh derive the marker key
        independently, and the second resolves a PWF_PLAN_ROOT pin while the
        first does not. If the two spellings diverged, the marker would never
        be cleared and the nudge would degrade to once per SESSION with no
        error anywhere.

        Agreement is proven by deletion: the re-arm must remove the exact file
        the throttle wrote. A leftover slot means it deleted a different key
        and the two sides are out of step.
        """
        self._codex("post-tool-use.sh")
        written = sorted((self.cache / "pwf-turn").glob("*"))
        self.assertEqual(1, len(written), "the throttle wrote no marker to agree on")

        self._codex("user-prompt-submit.sh")
        left = sorted((self.cache / "pwf-turn").glob("*"))
        self.assertEqual([], left, f"re-arm deleted a different key, stale slots: {left}")

    def test_two_sessions_do_not_silence_each_others_first_nudge(self):
        self.assertIn(NUDGE, self._claude("post-tool-use", PWF_SESSION_ID="alpha"))
        self.assertEqual("", self._claude("post-tool-use", PWF_SESSION_ID="alpha").strip())
        self.assertIn(NUDGE, self._claude("post-tool-use", PWF_SESSION_ID="beta"))

    def test_a_broken_cache_root_skips_the_throttle_not_the_nudge(self):
        """Fail toward the reminder, never toward silence."""
        env_extra = {"XDG_CACHE_HOME": str(self.root / "task_plan.md")}  # a file, not a dir
        first = self._claude("post-tool-use", **env_extra)
        second = self._claude("post-tool-use", **env_extra)
        self.assertIn(NUDGE, first)
        self.assertIn(NUDGE, second)

    # --- defect 3: the matcher ----------------------------------------------

    def test_bash_is_off_the_post_tool_matchers_and_still_on_pre_tool(self):
        for manifest in (
            REPO_ROOT / "hooks" / "hooks.json",
            REPO_ROOT / "hooks" / "codex-hooks.json",
            REPO_ROOT / ".codex" / "hooks.json",
        ):
            with self.subTest(manifest=manifest.name):
                data = json.loads(manifest.read_text(encoding="utf-8"))
                node = data.get("hooks", data)
                post = [b.get("matcher", "") for b in node["PostToolUse"]]
                self.assertTrue(post, manifest)
                for matcher in post:
                    self.assertNotIn("Bash", matcher)
                    self.assertIn("Write", matcher)
                    self.assertIn("Edit", matcher)
                # A pre-tool plan reminder before a shell command is a
                # different, wanted behaviour and must not be collateral.
                for matcher in [b.get("matcher", "") for b in node["PreToolUse"]]:
                    self.assertIn("Bash", matcher)

    # --- the #237 gap this issue exposed in the plugin dispatcher -----------

    def test_plugin_dispatcher_honors_a_rejected_plan_id_binding(self):
        """hooks/claude-hook.sh resolves through the shared resolver and then
        fell back to the legacy root plan, the fallback v3.15.0 removed from
        the script and Codex routes but not from this one."""
        planning = self.root / ".planning" / "2026-09-02-real"
        planning.mkdir(parents=True)
        (planning / "task_plan.md").write_text("# real\n", encoding="utf-8")
        out = self._claude("post-tool-use", PLAN_ID="2026-09-02-ghost")
        self.assertEqual("", out.strip())


if __name__ == "__main__":
    unittest.main()
