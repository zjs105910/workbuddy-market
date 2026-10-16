"""get_claude_project_dir mapping tests (v3.8.0 regression fix).

Claude Code keeps underscores and the leading dash of POSIX absolute paths
in ~/.claude/projects/ names. The pre-v3.8.0 mapper replaced '_' with '-'
and stripped the leading dash, silently missing the real store on every
macOS/Linux install and on any project path with an underscore (verified
against real stores on disk). These tests pin the corrected candidate-set
mapping and its legacy fallbacks.
"""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT_SOURCE = (
    Path(__file__).resolve().parents[1]
    / "skills/planning-with-files/scripts/session-catchup.py"
)


def load_module(script_path: Path):
    spec = importlib.util.spec_from_file_location(
        "session_catchup_projdir", script_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ClaudeProjectDirMappingTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.home = Path(self.tempdir.name)
        self.projects = self.home / ".claude" / "projects"
        self.projects.mkdir(parents=True)
        self.module = load_module(SCRIPT_SOURCE)
        self.home_patch = mock.patch.object(
            self.module.Path, "home", return_value=self.home
        )
        self.home_patch.start()
        # The surface under test is sanitize+probe, not path resolution.
        self.norm_patch = mock.patch.object(
            self.module, "normalize_path", side_effect=lambda p: p
        )
        self.norm_patch.start()

    def tearDown(self):
        self.norm_patch.stop()
        self.home_patch.stop()
        self.tempdir.cleanup()

    def _mk(self, name: str) -> Path:
        d = self.projects / name
        d.mkdir()
        return d

    def test_windows_underscore_path_kept(self):
        real = self._mk("C--Users-dev-Documents-My_Repo")
        got = self.module.get_claude_project_dir("C:\\Users\\dev\\Documents\\My_Repo")
        self.assertEqual(real, got)

    def test_posix_leading_dash_kept(self):
        real = self._mk("-home-dev-project")
        got = self.module.get_claude_project_dir("/home/dev/project")
        self.assertEqual(real, got)

    def test_posix_underscore_and_dash_kept(self):
        real = self._mk("-home-dev-Ayseu_Visa_2026")
        got = self.module.get_claude_project_dir("/home/dev/Ayseu_Visa_2026")
        self.assertEqual(real, got)

    def test_dot_becomes_dash(self):
        real = self._mk("-home-dev-my-app-v2")
        got = self.module.get_claude_project_dir("/home/dev/my.app.v2")
        self.assertEqual(real, got)

    def test_legacy_underscore_spelling_still_found(self):
        legacy = self._mk("C--Users-dev-My-Repo")
        got = self.module.get_claude_project_dir("C:\\Users\\dev\\My_Repo")
        self.assertEqual(legacy, got)

    def test_legacy_stripped_dash_still_found(self):
        legacy = self._mk("home-dev-project")
        got = self.module.get_claude_project_dir("/home/dev/project")
        self.assertEqual(legacy, got)

    def test_collision_resolved_by_session_cwd(self):
        primary = self._mk("-home-dev-foo_bar")
        legacy = self._mk("-home-dev-foo-bar")
        (legacy / "s1.jsonl").write_text(
            json.dumps({"cwd": "/home/dev/foo-bar"}) + "\n", encoding="utf-8"
        )
        (primary / "s1.jsonl").write_text(
            json.dumps({"cwd": "/home/dev/foo_bar"}) + "\n", encoding="utf-8"
        )
        self.assertEqual(
            primary, self.module.get_claude_project_dir("/home/dev/foo_bar")
        )
        self.assertEqual(
            legacy, self.module.get_claude_project_dir("/home/dev/foo-bar")
        )

    def test_missing_store_returns_primary_spelling(self):
        got = self.module.get_claude_project_dir("/home/dev/absent_proj")
        self.assertEqual(self.projects / "-home-dev-absent_proj", got)


if __name__ == "__main__":
    unittest.main()
