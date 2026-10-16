"""Regression coverage for shell-script bytes in the published npm package."""

from __future__ import annotations

import json
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / ".pi" / "skills" / "planning-with-files"
VERIFIER = PACKAGE_ROOT / "scripts" / "verify-shell-line-endings.mjs"
VERIFIER_MEMBER = "package/scripts/verify-shell-line-endings.mjs"


def _find_executable(name: str) -> str | None:
    """Resolve commands with PATHEXT support on Windows."""
    executable = shutil.which(name)
    if executable is None and name == "npm":
        executable = shutil.which("npm.cmd")
    return executable


class NpmPackageLineEndingTests(unittest.TestCase):
    def test_manifest_runs_line_ending_verifier_before_pack(self) -> None:
        manifest = json.loads((PACKAGE_ROOT / "package.json").read_text("utf-8"))
        self.assertEqual(
            "node scripts/verify-shell-line-endings.mjs",
            manifest.get("scripts", {}).get("prepack"),
        )

    def test_verifier_accepts_package_quietly(self) -> None:
        node = _find_executable("node")
        if node is None:
            self.skipTest("node is unavailable")

        result = subprocess.run(
            [node, str(VERIFIER)],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stdout)
        self.assertEqual("", result.stderr)

    def test_verifier_rejects_corrupted_fixture(self) -> None:
        node = _find_executable("node")
        if node is None:
            self.skipTest("node is unavailable")

        with tempfile.TemporaryDirectory() as temp_dir:
            fixture_root = Path(temp_dir)
            scripts_root = fixture_root / "scripts"
            scripts_root.mkdir()
            (scripts_root / "clean.sh").write_bytes(b"#!/bin/sh\necho clean\n")
            (scripts_root / "z-corrupted.sh").write_bytes(
                b"#!/bin/sh\r\necho corrupted\r\n"
            )
            (scripts_root / "a-corrupted.sh").write_bytes(
                b"#!/bin/sh\r\necho corrupted\r\n"
            )

            result = subprocess.run(
                [node, str(VERIFIER), str(fixture_root)],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

        self.assertNotEqual(0, result.returncode)
        self.assertEqual("", result.stdout)
        self.assertIn("scripts/a-corrupted.sh", result.stderr)
        self.assertIn("scripts/z-corrupted.sh", result.stderr)
        self.assertLess(
            result.stderr.index("scripts/a-corrupted.sh"),
            result.stderr.index("scripts/z-corrupted.sh"),
        )

    def test_verifier_rejects_package_without_shell_scripts(self) -> None:
        node = _find_executable("node")
        if node is None:
            self.skipTest("node is unavailable")

        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_root = Path(temp_dir) / "scripts"
            scripts_root.mkdir()
            result = subprocess.run(
                [node, str(VERIFIER), temp_dir],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

        self.assertNotEqual(0, result.returncode)
        self.assertEqual("", result.stdout)
        self.assertIn("No shell scripts found", result.stderr)

    def test_npm_tarball_contains_only_lf_shell_scripts(self) -> None:
        npm = _find_executable("npm")
        if npm is None:
            self.skipTest("npm is unavailable")

        source_scripts = sorted((PACKAGE_ROOT / "scripts").glob("*.sh"))
        self.assertTrue(source_scripts, "package source has no scripts/*.sh files")
        expected_members = {
            f"package/scripts/{script.name}" for script in source_scripts
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            pack_result = subprocess.run(
                [npm, "pack", "--pack-destination", temp_dir],
                cwd=PACKAGE_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(
                0,
                pack_result.returncode,
                f"npm pack failed:\n{pack_result.stdout}\n{pack_result.stderr}",
            )

            tarballs = list(Path(temp_dir).glob("*.tgz"))
            self.assertEqual(1, len(tarballs), pack_result.stdout)
            with tarfile.open(tarballs[0], mode="r:gz") as archive:
                members = {member.name: member for member in archive.getmembers()}
                self.assertIn(
                    VERIFIER_MEMBER,
                    members,
                    "packed package lost the verifier used by its prepack lifecycle",
                )
                actual_members = {
                    name
                    for name in members
                    if name.startswith("package/scripts/") and name.endswith(".sh")
                }
                self.assertEqual(expected_members, actual_members)
                offenders = []
                for name in sorted(actual_members):
                    extracted = archive.extractfile(members[name])
                    self.assertIsNotNone(extracted, name)
                    if b"\r" in extracted.read():
                        offenders.append(name)

        self.assertEqual([], offenders, f"tarball scripts contain CR: {offenders}")


if __name__ == "__main__":
    unittest.main()
