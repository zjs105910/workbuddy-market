"""Hook scripts that a host runs by path must be executable in the git index.

Gemini CLI runs every hook command through `bash -c <command>`, and Cursor's
hook documentation requires `chmod +x` for script hooks. A script committed as
100644 therefore fails with "Permission denied" in a macOS or Linux clone and
the hook silently does nothing. Routes that name an interpreter explicitly
(`sh script`, Copilot's "bash" key, `python3 run_sh.py`) do not need the bit
and are not checked here.
"""
from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
GIT = shutil.which("git")


def scripts_run_by_path() -> list[tuple[str, str]]:
    """(manifest, repo-relative script) for each hook command that runs a .sh by path."""
    found = []
    cursor = json.loads((REPO / ".cursor" / "hooks.json").read_text(encoding="utf-8"))
    for entries in cursor["hooks"].values():
        for entry in entries:
            program = shlex.split(entry["command"])[0]
            if program.endswith(".sh"):
                found.append((".cursor/hooks.json", program))
    gemini = json.loads((REPO / ".gemini" / "settings.json").read_text(encoding="utf-8"))
    for groups in gemini["hooks"].values():
        for group in groups:
            for hook in group["hooks"]:
                program = shlex.split(hook["command"])[0]
                if program.endswith(".sh"):
                    found.append(
                        (".gemini/settings.json", program.replace("$GEMINI_PROJECT_DIR/", "", 1))
                    )
    return found


def index_modes(paths: list[str]) -> dict[str, str]:
    result = subprocess.run(
        [GIT or "git", "ls-files", "-s", "--", *paths],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    modes = {}
    for line in result.stdout.splitlines():
        meta, path = line.split("\t", 1)
        modes[path] = meta.split()[0]
    return modes


@unittest.skipUnless(GIT and (REPO / ".git").exists(), "requires a git checkout")
class HookScriptModeTests(unittest.TestCase):
    def test_scripts_run_by_path_are_executable_in_the_index(self) -> None:
        scripts = scripts_run_by_path()
        self.assertTrue(scripts, "no hook script found in the Cursor or Gemini manifest")
        modes = index_modes([path for _, path in scripts])
        for manifest, path in scripts:
            with self.subTest(manifest=manifest, script=path):
                self.assertEqual(
                    "100755",
                    modes.get(path),
                    f"{path} is run by path from {manifest} but is not executable",
                )


if __name__ == "__main__":
    unittest.main()
