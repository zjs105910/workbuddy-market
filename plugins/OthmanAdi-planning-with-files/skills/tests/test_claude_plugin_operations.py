"""Focused operational contract for the Claude Code plugin route."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
DESCRIPTOR = ROOT / "hooks" / "hooks.json"
LAUNCHER = ROOT / "hooks" / "claude-hook.sh"
SKILL = ROOT / "skills" / "planning-with-files" / "SKILL.md"
PLUGIN_MANIFEST = ROOT / ".claude-plugin" / "plugin.json"
PLAN_ATTEST = ROOT / "commands" / "plan-attest.md"
SH = shutil.which("sh")


def _frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    _, raw, _ = text.split("---", 2)
    return yaml.safe_load(raw)


@unittest.skipUnless(SH, "Git/POSIX sh is required for Claude hook tests")
class ClaudePluginDescriptorTests(unittest.TestCase):
    def test_descriptor_is_plugin_rooted_and_complete(self) -> None:
        payload = json.loads(DESCRIPTOR.read_text(encoding="utf-8"))
        hooks = payload["hooks"]
        self.assertEqual(
            {
                "SessionStart",
                "UserPromptSubmit",
                "PreToolUse",
                "PostToolUse",
                "PreCompact",
                "Stop",
            },
            set(hooks),
        )
        self.assertEqual("startup|resume|clear|compact", hooks["SessionStart"][0]["matcher"])
        self.assertEqual("Write|Edit|Bash|Read|Glob|Grep", hooks["PreToolUse"][0]["matcher"])
        # Bash came off PostToolUse in v3.16.0 (#239): ls and git status were
        # tripping a "you changed something, record it" reminder. PreToolUse
        # above keeps Bash, which is a different and wanted behaviour.
        self.assertEqual("Write|Edit", hooks["PostToolUse"][0]["matcher"])

        for groups in hooks.values():
            for group in groups:
                for hook in group["hooks"]:
                    self.assertEqual("sh", hook["command"])
                    self.assertEqual(
                        "${CLAUDE_PLUGIN_ROOT}/hooks/claude-hook.sh",
                        hook["args"][0],
                    )

        serialized = json.dumps(payload)
        self.assertNotIn("CLAUDE_SKILL_DIR", serialized)
        self.assertNotIn("$HOME", serialized)
        self.assertNotIn(".claude/plugins/marketplaces", serialized)

    def test_claude_manifest_does_not_duplicate_conventional_descriptor(self) -> None:
        manifest = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))
        self.assertNotIn("hooks", manifest)


@unittest.skipUnless(SH, "Git/POSIX sh is required for Claude hook tests")
class ClaudePluginLauncherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.plugin = self.base / "plugin cache with spaces"
        self.project = self.base / "project with spaces"
        (self.plugin / "hooks").mkdir(parents=True)
        (self.plugin / "scripts").mkdir()
        self.project.mkdir()
        shutil.copy2(LAUNCHER, self.plugin / "hooks" / LAUNCHER.name)
        self.env = os.environ.copy()
        for name in ("PLAN_ID", "PWF_PLAN_ROOT", "PWF_SESSION_ID"):
            self.env.pop(name, None)
        sh_usr_bin = str(Path(SH).parent)
        path_entries = [sh_usr_bin]
        if os.name == "nt":
            path_entries.insert(0, str(Path(SH).parents[2] / "bin"))
        path_entries.append(self.env.get("PATH", ""))
        self.env.update(
            {
                "CLAUDE_PLUGIN_ROOT": str(self.plugin),
                "HOME": str(self.base / "isolated-home"),
                "USERPROFILE": str(self.base / "isolated-home"),
                "XDG_CACHE_HOME": str(self.base / "isolated-cache"),
                "PATH": os.pathsep.join(path_entries),
            }
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_script(self, name: str, body: str) -> None:
        (self.plugin / "scripts" / name).write_text(body, encoding="utf-8", newline="\n")

    def _run(self, event: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [SH, str(self.plugin / "hooks" / LAUNCHER.name), event],
            cwd=self.project,
            env=self.env,
            input=stdin,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )

    def test_session_start_is_silent_without_active_plan(self) -> None:
        self._write_script("resolve-plan-dir.sh", "#!/bin/sh\n[ -f task_plan.md ] && pwd\n")
        self._write_script("inject-plan.sh", "#!/bin/sh\necho SHOULD_NOT_RUN\n")
        self._write_script("session-catchup.py", "print('SHOULD_NOT_RUN')\n")

        result = self._run("session-start")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stdout)

    def test_session_start_uses_no_history_catchup_before_injection(self) -> None:
        (self.project / "task_plan.md").write_text("# Claude plan\n", encoding="utf-8")
        self._write_script("resolve-plan-dir.sh", "#!/bin/sh\npwd\n")
        self._write_script(
            "inject-plan.sh",
            "#!/bin/sh\nprintf 'Windows C:\\\\Users\\\\name; literal \\\\n; tab\\tbad; carriage\\rvalue\\nsecond'\n",
        )
        self._write_script(
            "session-catchup.py",
            "import sys\n"
            "assert '--no-history' in sys.argv\n"
            "assert '--metadata' not in sys.argv\n"
            "assert '--replay' not in sys.argv\n"
            "print('CATCHUP FIRST')\n",
        )

        result = self._run("session-start")

        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        output = payload["hookSpecificOutput"]
        self.assertEqual("SessionStart", output["hookEventName"])
        self.assertEqual(
            "CATCHUP FIRST\nWindows C:\\Users\\name; literal \\n; tab bad; carriage value\nsecond",
            output["additionalContext"],
        )

    def test_stop_preserves_original_stdin(self) -> None:
        self._write_script("gate-stop.sh", "#!/bin/sh\ncat\n")
        original = '{"stop_hook_active":true,"cwd":"C:\\\\repo with spaces"}'

        result = self._run("stop", original)

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(original, json.loads(result.stdout)["systemMessage"])

    def test_missing_plugin_root_never_falls_back_to_mutable_home_install(self) -> None:
        fake = self.base / "isolated-home" / ".claude" / "plugins" / "marketplaces" / "planning-with-files" / "scripts"
        fake.mkdir(parents=True)
        (fake / "inject-plan.sh").write_text("echo MUTABLE_SOURCE_RAN\n", encoding="utf-8")
        env = self.env.copy()
        env.pop("CLAUDE_PLUGIN_ROOT")

        result = subprocess.run(
            [SH, str(self.plugin / "hooks" / LAUNCHER.name), "session-start"],
            cwd=self.project,
            env=env,
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stdout)

    def test_real_hardened_scripts_run_from_cached_path_with_spaces(self) -> None:
        shutil.rmtree(self.plugin / "scripts")
        shutil.copytree(ROOT / "scripts", self.plugin / "scripts")
        (self.project / "task_plan.md").write_text(
            "# Cached Claude plan\n\n### Phase 1\n**Status:** in_progress\n",
            encoding="utf-8",
        )
        (self.project / "progress.md").write_text("- cache-safe\n", encoding="utf-8")

        result = self._run("session-start")

        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        context = payload["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Cached Claude plan", context)
        self.assertIn("cache-safe", context)


@unittest.skipUnless(SH, "Git/POSIX sh is required for Claude hook tests")
class ClaudePluginExactlyOnceTests(unittest.TestCase):
    def test_skill_hooks_are_noops_in_plugin_context(self) -> None:
        hooks = _frontmatter(SKILL)["hooks"]
        commands = [
            hook["command"]
            for groups in hooks.values()
            for group in groups
            for hook in group["hooks"]
        ]
        self.assertEqual(5, len(commands))
        for command in commands:
            self.assertTrue(command.startswith('[ -n "${CLAUDE_PLUGIN_ROOT:-}" ] && exit 0;'))
            result = subprocess.run(
                [SH, "-c", command],
                env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(ROOT)},
                text=True,
                capture_output=True,
                timeout=15,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("", result.stdout)

    def test_standalone_skill_hook_remains_activation_scoped(self) -> None:
        command = _frontmatter(SKILL)["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            project = base / "standalone project"
            skill = base / "standalone skill"
            project.mkdir()
            shutil.copytree(ROOT / "scripts", skill / "scripts")
            (project / "task_plan.md").write_text("# Standalone plan\n", encoding="utf-8")
            (project / "progress.md").write_text("", encoding="utf-8")
            env = os.environ.copy()
            env.pop("CLAUDE_PLUGIN_ROOT", None)
            env.update(
                {
                    "CLAUDE_SKILL_DIR": str(skill),
                    "HOME": str(base / "home"),
                    "XDG_CACHE_HOME": str(base / "cache"),
                }
            )
            result = subprocess.run(
                [SH, "-c", command],
                cwd=project,
                env=env,
                text=True,
                capture_output=True,
                timeout=15,
                check=False,
            )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("Standalone plan", result.stdout)

    def test_plan_attest_documents_plugin_root_before_standalone_fallback(self) -> None:
        text = PLAN_ATTEST.read_text(encoding="utf-8")
        plugin = '$env:CLAUDE_PLUGIN_ROOT\\scripts\\attest-plan.ps1'
        standalone = '$env:USERPROFILE\\.claude\\skills\\planning-with-files\\scripts\\attest-plan.ps1'
        self.assertIn(plugin, text)
        self.assertIn(standalone, text)
        self.assertLess(text.index(plugin), text.index(standalone))


if __name__ == "__main__":
    unittest.main()
