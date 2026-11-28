"""Test the path sanitization in scripts/session-catchup.py.

Loads the real module via importlib (the filename has a hyphen, so it can't
be `import`-ed normally) and exercises its actual get_project_dir_claude,
instead of reimplementing the logic here. An earlier version of this file
reimplemented a fixed sanitizer for testing "to avoid import issues" — that
reimplementation was correct, but it meant the suite stayed green while the
shipped session-catchup.py (which it never touched) was still broken on
Windows. See CHANGELOG for the fix this guards.
"""
import importlib.util
import os
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "scripts" / "session-catchup.py"

spec = importlib.util.spec_from_file_location("session_catchup", MODULE_PATH)
assert spec is not None and spec.loader is not None
session_catchup = importlib.util.module_from_spec(spec)
sys.modules["session_catchup"] = session_catchup
spec.loader.exec_module(session_catchup)


class SessionCatchupPathSanitizeTests(unittest.TestCase):
    def _sanitized_name(self, project_path: str) -> str:
        project_dir = session_catchup.get_project_dir_claude(project_path)
        return project_dir.name

    @unittest.skipUnless(os.name == "nt", "Windows-shaped input; on POSIX Path.resolve() treats C:/... as relative and prepends the CWD")
    def test_windows_native_path(self) -> None:
        result = self._sanitized_name("C:/Users/oasrvadmin/Documents/planning-with-files-repo")
        self.assertEqual(result, "C--Users-oasrvadmin-Documents-planning-with-files-repo")

    @unittest.skipUnless(os.name == "nt", "Windows-shaped input; on POSIX Path.resolve() treats C:/... as relative and prepends the CWD")
    def test_git_bash_path(self) -> None:
        result = self._sanitized_name("/c/Users/oasrvadmin/Documents/planning-with-files-repo")
        self.assertEqual(result, "C--Users-oasrvadmin-Documents-planning-with-files-repo")

    @unittest.skipIf(os.name == "nt", "exercises the real-Unix-path branch, not meaningful on Windows")
    def test_unix_absolute_path_unchanged(self) -> None:
        # Real Unix paths never contain ':' or '\\', so this must take the
        # legacy branch untouched by the Windows fix (regression guard).
        result = self._sanitized_name("/home/user/project")
        self.assertEqual(result, "-home-user-project")


if __name__ == "__main__":
    unittest.main()
