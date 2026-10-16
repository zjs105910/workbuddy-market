import base64
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_MANIFEST = REPO_ROOT / ".codex-plugin" / "plugin.json"
PLUGIN_HOOKS = REPO_ROOT / "hooks" / "codex-hooks.json"
STANDALONE_HOOKS = REPO_ROOT / ".codex" / "hooks.json"
STOP_HOOK = REPO_ROOT / ".codex" / "hooks" / "stop.py"
PLUGIN_DISPATCH = REPO_ROOT / ".codex" / "hooks" / "plugin_dispatch.py"

EXPECTED_EVENTS = {
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PermissionRequest",
    "PostToolUse",
    "PreCompact",
    "Stop",
}
# PreToolUse and PostToolUse stopped sharing a matcher in v3.16.0 (#239):
# a plan reminder BEFORE a shell command is wanted, a "record what you
# changed" nudge AFTER `ls` is not.
PRE_TOOL_MATCHER = "Bash|apply_patch|Edit|Write"
POST_TOOL_MATCHER = "apply_patch|Edit|Write"
EVENT_MATCHERS = {"PreToolUse": PRE_TOOL_MATCHER, "PostToolUse": POST_TOOL_MATCHER}
WINDOWS_DISPATCH = (
    "& (Join-Path $env:PLUGIN_ROOT '.codex\\hooks\\pwf-hook.cmd') "
    "plugin_dispatch.py"
)


class CodexPluginOperationsTests(unittest.TestCase):
    def run_stop(self, root: Path, stop_hook_active: bool) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [os.sys.executable, str(STOP_HOOK)],
            input=json.dumps({"cwd": str(root), "stop_hook_active": stop_hook_active}),
            text=True,
            encoding="utf-8",
            capture_output=True,
            cwd=root,
            check=False,
        )

    @staticmethod
    def write_plan(root: Path, status: str, gated: bool = False) -> None:
        root.joinpath("task_plan.md").write_text(
            f"### Phase 1: Codex operations\n- **Status:** {status}\n",
            encoding="utf-8",
        )
        if gated:
            root.joinpath(".mode").write_text("autonomous gate\n", encoding="utf-8")

    def test_manifest_selects_one_skill_root_and_codex_only_hooks(self) -> None:
        manifest = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))

        self.assertEqual("planning-with-files", manifest["name"])
        self.assertEqual("./.agents/skills/", manifest["skills"])
        # Omitting commands makes Codex migrate the top-level Claude commands
        # into redundant source-command-* skills even with an explicit skills root.
        self.assertEqual([], manifest.get("commands"), "Disable Codex's legacy command fallback")
        self.assertEqual("./hooks/codex-hooks.json", manifest["hooks"])
        self.assertNotIn("hooks/hooks.json", manifest.values())

        skill_dirs = [path for path in (REPO_ROOT / ".agents" / "skills").iterdir() if path.is_dir()]
        self.assertEqual(["planning-with-files"], sorted(path.name for path in skill_dirs))
        self.assertTrue(skill_dirs[0].joinpath("SKILL.md").is_file())

    def test_plugin_and_standalone_descriptors_cover_same_codex_events(self) -> None:
        plugin = json.loads(PLUGIN_HOOKS.read_text(encoding="utf-8"))
        standalone = json.loads(STANDALONE_HOOKS.read_text(encoding="utf-8"))

        self.assertEqual(EXPECTED_EVENTS, set(plugin["hooks"]))
        self.assertEqual(EXPECTED_EVENTS, set(standalone["hooks"]))
        for event, matcher in EVENT_MATCHERS.items():
            self.assertEqual(matcher, plugin["hooks"][event][0]["matcher"])
            self.assertEqual(matcher, standalone["hooks"][event][0]["matcher"])

    def test_plugin_commands_are_cache_rooted_and_do_not_fallback_to_standalone(self) -> None:
        descriptor = json.loads(PLUGIN_HOOKS.read_text(encoding="utf-8"))

        for event, entries in descriptor["hooks"].items():
            for entry in entries:
                for hook in entry["hooks"]:
                    command = hook["command"]
                    command_windows = hook["commandWindows"]
                    self.assertIn("${PLUGIN_ROOT}", command, event)
                    self.assertIn("/.codex/hooks/", command, event)
                    self.assertNotIn('"', command_windows, event)
                    self.assertNotIn("cmd /d /s /c", command_windows.lower(), event)
                    encoded = command_windows.rsplit(" ", 1)[-1]
                    decoded = base64.b64decode(encoded).decode("utf-16-le")
                    self.assertEqual(WINDOWS_DISPATCH, decoded, event)
                    self.assertNotIn("$HOME", command, event)
                    self.assertNotIn("||", command, event)
                    self.assertNotIn(".codex/hooks/", command.replace("${PLUGIN_ROOT}/.codex/hooks/", ""), event)

    def test_windows_dispatcher_routes_every_supported_event(self) -> None:
        expected = {
            "SessionStart": ("run_sh.py", "session-start.sh"),
            "UserPromptSubmit": ("run_sh.py", "user-prompt-submit.sh"),
            "PreToolUse": ("pre_tool_use.py",),
            "PermissionRequest": ("permission_request.py",),
            "PostToolUse": ("post_tool_use.py",),
            "PreCompact": ("run_sh.py", "pre-compact.sh"),
            "Stop": ("stop.py",),
        }
        source = PLUGIN_DISPATCH.read_text(encoding="utf-8")
        stub = (
            "import json, pathlib, sys\n"
            "payload = json.load(sys.stdin)\n"
            "print(json.dumps({'script': pathlib.Path(__file__).name, "
            "'args': sys.argv[1:], 'event': payload['hook_event_name']}))\n"
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            hooks_dir = Path(tmpdir) / ".codex" / "hooks"
            hooks_dir.mkdir(parents=True)
            hooks_dir.joinpath("plugin_dispatch.py").write_text(source, encoding="utf-8")
            for script in {route[0] for route in expected.values()}:
                hooks_dir.joinpath(script).write_text(stub, encoding="utf-8")

            for event, route in expected.items():
                result = subprocess.run(
                    [os.sys.executable, str(hooks_dir / "plugin_dispatch.py")],
                    input=json.dumps({"hook_event_name": event}),
                    text=True,
                    encoding="utf-8",
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(0, result.returncode, f"{event}: {result.stderr}")
                output = json.loads(result.stdout)
                self.assertEqual(route[0], output["script"])
                self.assertEqual(list(route[1:]), output["args"])
                self.assertEqual(event, output["event"])

    def test_gated_in_progress_stop_blocks_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self.write_plan(root, "in_progress", gated=True)
            result = self.run_stop(root, stop_hook_active=False)

        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("block", payload["decision"])
        self.assertIn("Codex operations", payload["reason"])

    def test_active_stop_hook_never_reblocks_gated_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self.write_plan(root, "in_progress", gated=True)
            result = self.run_stop(root, stop_hook_active=True)

        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertNotIn("decision", payload)
        self.assertIn("Task in progress", payload["systemMessage"])

    def test_legacy_in_progress_stop_stays_advisory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self.write_plan(root, "in_progress", gated=False)
            result = self.run_stop(root, stop_hook_active=False)

        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertNotIn("decision", payload)
        self.assertIn("Task in progress", payload["systemMessage"])

    def test_complete_gated_plan_allows_stop_silently(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self.write_plan(root, "complete", gated=True)
            result = self.run_stop(root, stop_hook_active=False)

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stdout.strip())

    def test_stop_is_silent_without_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self.run_stop(Path(tmpdir), stop_hook_active=False)

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stdout.strip())

    @unittest.skipUnless(os.name == "nt", "commandWindows execution is Windows-specific")
    def test_command_windows_runs_from_spaced_cached_root(self) -> None:
        descriptor = json.loads(PLUGIN_HOOKS.read_text(encoding="utf-8"))
        source_hooks = REPO_ROOT / ".codex" / "hooks"

        with tempfile.TemporaryDirectory(prefix="pwf codex cache ") as tmpdir:
            plugin_root = Path(tmpdir) / "planning with files" / "3.11.2"
            cached_hooks = plugin_root / ".codex" / "hooks"
            shutil.copytree(source_hooks, cached_hooks)
            project = Path(tmpdir) / "project with spaces"
            project.mkdir()
            project.joinpath("task_plan.md").write_text("# Task Plan\n", encoding="utf-8")

            hook = descriptor["hooks"]["PostToolUse"][0]["hooks"][0]
            command = hook["commandWindows"]
            env = os.environ.copy()
            env["PLUGIN_ROOT"] = str(plugin_root)
            env["PLUGIN_DATA"] = str(Path(tmpdir) / "plugin data")
            result = subprocess.run(
                command,
                input=json.dumps(
                    {
                        "hook_event_name": "PostToolUse",
                        "cwd": str(project),
                        "tool_name": "apply_patch",
                        "tool_response": "ok",
                    }
                ),
                text=True,
                encoding="utf-8",
                capture_output=True,
                cwd=project,
                env=env,
                shell=True,
                check=False,
            )

        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        # The post-tool nudge moved to additionalContext in v3.16.0 (#239).
        block = payload["hookSpecificOutput"]
        self.assertEqual("PostToolUse", block["hookEventName"])
        self.assertIn("progress.md", block["additionalContext"])


if __name__ == "__main__":
    unittest.main()
