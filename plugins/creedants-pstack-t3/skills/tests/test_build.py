import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CASES = (
    ("t3/added/brigade/scripts/brigade.py", "brigade/scripts/brigade.py", 0o644),
    ("t3/added/brigade-admin/SKILL.md", "brigade-admin/SKILL.md", None),
    ("t3/added/landing/scripts/land.py", "landing/scripts/land.py", 0o644),
    (
        "vendor/pstack/skills/poteto-mode/scripts/watch-pr/watch-pr",
        "poteto-mode/scripts/watch-pr/watch-pr",
        0o755,
    ),
    ("t3/scripts/roles.py", "pstack-runtime/scripts/roles.py", None),
    (
        "t3/overrides/poteto-mode/scripts/check-plan.mjs",
        "poteto-mode/scripts/check-plan.mjs",
        None,
    ),
    (
        "t3/overrides/poteto-mode/scripts/worktree-audit.sh",
        "poteto-mode/scripts/worktree-audit.sh",
        None,
    ),
    (
        "vendor/pstack/skills/poteto-mode/scripts/orch/orch.ts",
        "poteto-mode/scripts/orch/orch.ts",
        None,
    ),
    ("t3/runtime.md", "pstack-runtime/SKILL.md", None),
)


class BuildModeTest(unittest.TestCase):
    def test_built_files_keep_source_modes(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "skills"
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/build.py"), "--out", str(out)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for source_rel, output_rel, expected in CASES:
                with self.subTest(path=output_rel):
                    source = ROOT / source_rel
                    built = out / output_rel
                    self.assertTrue(built.is_file(), output_rel)
                    source_mode = stat.S_IMODE(source.stat().st_mode)
                    built_mode = stat.S_IMODE(built.stat().st_mode)
                    self.assertEqual(built_mode, source_mode, output_rel)
                    if expected is not None:
                        self.assertEqual(source_mode, expected, source_rel)
                        self.assertEqual(built_mode, expected, output_rel)


class BuildReferenceTest(unittest.TestCase):
    def test_default_build_writes_the_committed_command_line_reference_pages(self):
        if shutil.which("git") is None:
            self.skipTest("git is not installed, so the tracked tree cannot be listed")
        listed = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split("\0")
        with tempfile.TemporaryDirectory() as directory:
            copy = Path(directory)
            for rel in listed:
                if rel and not rel.startswith("docs/cli/") and (ROOT / rel).is_file():
                    (copy / rel).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(ROOT / rel, copy / rel)
            result = subprocess.run(
                [sys.executable, str(copy / "scripts/build.py")],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            built = sorted(path.name for path in (copy / "docs/cli").iterdir())
            self.assertEqual(built, sorted(path.name for path in (ROOT / "docs/cli").iterdir()))
            for name in built:
                with self.subTest(name):
                    self.assertEqual((copy / "docs/cli" / name).read_text(), (ROOT / "docs/cli" / name).read_text())
