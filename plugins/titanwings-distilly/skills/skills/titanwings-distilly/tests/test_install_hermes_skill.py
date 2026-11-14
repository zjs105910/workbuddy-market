from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys


TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from install_hermes_skill import install_skill  # noqa: E402


class HermesInstallTest(unittest.TestCase):
    def test_install_skill_copies_repo_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            source = Path(tmp_dir) / "source"
            destination = Path(tmp_dir) / "dest" / "distilly"
            source.mkdir()
            (source / "SKILL.md").write_text("name: distilly\n", encoding="utf-8")
            (source / "README.md").write_text("# Distilly\n", encoding="utf-8")

            installed = install_skill(source, destination)
            self.assertEqual(installed, destination)
            self.assertTrue((destination / "SKILL.md").exists())
            self.assertTrue((destination / "README.md").exists())

    def test_install_skill_dry_run_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            source = Path(tmp_dir) / "source"
            destination = Path(tmp_dir) / "dest" / "distilly"
            source.mkdir()
            (source / "SKILL.md").write_text("name: distilly\n", encoding="utf-8")

            install_skill(source, destination, dry_run=True)
            self.assertFalse(destination.exists())

    def test_install_skill_dry_run_allows_existing_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            source = Path(tmp_dir) / "source"
            destination = Path(tmp_dir) / "dest" / "distilly"
            source.mkdir(parents=True)
            destination.mkdir(parents=True)
            (source / "SKILL.md").write_text("name: distilly\n", encoding="utf-8")

            result = install_skill(source, destination, dry_run=True)
            self.assertEqual(result, destination)
            self.assertTrue(destination.exists())

    def test_install_skill_does_not_delete_source_when_it_is_already_the_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            source = Path(tmp_dir) / "distilly"
            source.mkdir()
            skill_file = source / "SKILL.md"
            skill_file.write_text("name: distilly\n", encoding="utf-8")

            result = install_skill(source, source, force=True)

            self.assertEqual(result, source)
            self.assertTrue(skill_file.exists())

    def test_install_skill_rejects_nested_or_ancestor_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "parent" / "source"
            source.mkdir(parents=True)
            skill_file = source / "SKILL.md"
            skill_file.write_text("name: distilly\n", encoding="utf-8")
            nested = source / ".hermes" / "skills" / "distilly"

            with self.assertRaisesRegex(ValueError, "must not overlap"):
                install_skill(source, nested, force=True)
            with self.assertRaisesRegex(ValueError, "must not overlap"):
                install_skill(source, source.parent, force=True)

            self.assertTrue(skill_file.exists())
            self.assertFalse(nested.exists())


if __name__ == "__main__":
    unittest.main()
