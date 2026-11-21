"""Hostile tests for the shared Codex/Hermes context reader and frame."""
from __future__ import annotations

import hashlib
import importlib.util
import os
import re
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
HELPERS = (
    REPO_ROOT / ".codex" / "hooks" / "context_frame.py",
    REPO_ROOT / ".hermes" / "plugins" / "planning-with-files" / "context_frame.py",
)


def load_helper(path: Path, index: int):
    spec = importlib.util.spec_from_file_location(f"pwf_context_frame_{index}", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


MODULES = tuple(load_helper(path, index) for index, path in enumerate(HELPERS))


class ContextFrameSecurityTests(unittest.TestCase):
    def test_helpers_are_byte_identical(self) -> None:
        self.assertEqual(HELPERS[0].read_bytes(), HELPERS[1].read_bytes())

    def test_valid_regular_file_reads_and_frame_metadata_match_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "plan.md"
            payload = "alpha\nβeta\n".encode("utf-8")
            source.write_bytes(payload)
            for module in MODULES:
                with self.subTest(module=module.__name__):
                    self.assertEqual(payload, module.read_regular_bytes(source))
                    framed = module.verified_frame("plan", source)
                    digest = hashlib.sha256(payload).hexdigest()
                    nonce = hashlib.sha256(
                        b"planning-with-files-context-v1\0plan\0" + payload
                    ).hexdigest()[:24]
                    self.assertIn(f"bytes={len(payload)} sha256={digest}", framed)
                    self.assertIn(f"nonce={nonce}", framed)
                    self.assertIn("truncated=false", framed)

    def test_only_verified_darwin_system_aliases_are_trusted(self) -> None:
        alias_info = SimpleNamespace(st_mode=stat.S_IFLNK)
        directory_info = SimpleNamespace(st_mode=stat.S_IFDIR)
        mappings = {
            "/var": ("private/var", "/private/var"),
            "/tmp": ("private/tmp", "/private/tmp"),
            "/etc": ("private/etc", "/private/etc"),
        }
        for module in MODULES:
            for alias, (link_text, target) in mappings.items():
                with self.subTest(module=module.__name__, alias=alias):
                    with (
                        mock.patch.object(module.sys, "platform", "darwin"),
                        mock.patch.object(module.os.path, "abspath", return_value=alias),
                        mock.patch.object(module.os, "readlink", return_value=link_text),
                        mock.patch.object(module.os.path, "realpath", return_value=target),
                        mock.patch.object(module.Path, "lstat", return_value=directory_info),
                    ):
                        self.assertTrue(
                            module._is_trusted_darwin_system_alias(Path(alias), alias_info)
                        )

            with self.subTest(module=module.__name__, case="wrong-target"):
                with (
                    mock.patch.object(module.sys, "platform", "darwin"),
                    mock.patch.object(module.os.path, "abspath", return_value="/var"),
                    mock.patch.object(module.os, "readlink", return_value="private/evil"),
                    mock.patch.object(module.os.path, "realpath", return_value="/private/var"),
                    mock.patch.object(module.Path, "lstat", return_value=directory_info),
                ):
                    self.assertFalse(
                        module._is_trusted_darwin_system_alias(Path("/var"), alias_info)
                    )

            with self.subTest(module=module.__name__, case="unlisted-alias"):
                with mock.patch.object(module.sys, "platform", "darwin"):
                    self.assertFalse(
                        module._is_trusted_darwin_system_alias(
                            Path("/usr/local"), alias_info
                        )
                    )

            with self.subTest(module=module.__name__, case="non-darwin"):
                with mock.patch.object(module.sys, "platform", "linux"):
                    self.assertFalse(
                        module._is_trusted_darwin_system_alias(Path("/var"), alias_info)
                    )

    @unittest.skipUnless(sys.platform == "darwin", "Darwin system alias regression")
    def test_darwin_var_temp_path_reads_regular_file(self) -> None:
        if not Path("/var").is_symlink():
            self.skipTest("/var is not a system alias on this Darwin host")
        with tempfile.TemporaryDirectory(dir="/var/tmp") as tmp:
            source = Path(tmp) / "plan.md"
            source.write_bytes(b"darwin alias is valid\n")
            for module in MODULES:
                with self.subTest(module=module.__name__):
                    self.assertEqual(
                        b"darwin alias is valid\n", module.read_regular_bytes(source)
                    )

    @unittest.skipUnless(os.name == "nt", "Windows 8.3 alias regression")
    def test_windows_short_temp_alias_matches_long_handle_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            if "~" not in tmp:
                self.skipTest("TEMP does not use an 8.3 short-path spelling")
            source = Path(tmp) / "short-alias.md"
            source.write_bytes(b"short alias is valid\n")
            for module in MODULES:
                with self.subTest(module=module.__name__):
                    self.assertEqual(b"short alias is valid\n", module.read_regular_bytes(source))

    def test_head_and_tail_line_omission_are_reported_as_truncation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "many-lines.md"
            source.write_text("".join(f"line-{n}\n" for n in range(100)), encoding="utf-8")
            for module in MODULES:
                with self.subTest(module=module.__name__, selection="head"):
                    head = module.verified_frame("plan", source, head=50)
                    self.assertIn("line-0", head)
                    self.assertNotIn("line-99", head)
                    self.assertIn("truncated=true", head)
                with self.subTest(module=module.__name__, selection="tail"):
                    tail = module.verified_frame("progress", source, tail=20)
                    self.assertNotIn("line-0\n", tail)
                    self.assertIn("line-99", tail)
                    self.assertIn("truncated=true", tail)

    def test_progress_normalization_precedes_digest_and_nonce(self) -> None:
        raw = b"worked 2026-08-29T13:42:41.123+02:00\n"
        normalized = b"worked 2026-08-29T00:00:00+02:00\n"
        expected_digest = hashlib.sha256(normalized).hexdigest()
        for module in MODULES:
            with self.subTest(module=module.__name__):
                frame = module.frame_bytes("progress", raw)
                self.assertNotIn("13:42:41", frame)
                self.assertIn("T00:00:00+02:00", frame)
                self.assertIn(f"sha256={expected_digest}", frame)

    def test_missing_attestation_refuses_autonomous_and_gated_modes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = root / "task_plan.md"
            plan.write_text("# Plan\n", encoding="utf-8")
            mode = root / ".mode"
            for marker in ("autonomous\n", "autonomous gate\n"):
                mode.write_text(marker, encoding="ascii")
                for module in MODULES:
                    with self.subTest(module=module.__name__, marker=marker.strip()):
                        with self.assertRaisesRegex(ValueError, "requires attested plan"):
                            module.verified_frame(
                                "plan", plan, attestation=root / ".attestation", mode=mode
                            )

    def test_valid_v3_attestation_admits_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = root / "task_plan.md"
            plan.write_text("# Approved\n", encoding="utf-8")
            (root / ".mode").write_text("autonomous gate\n", encoding="ascii")
            (root / ".attestation").write_text(
                hashlib.sha256(plan.read_bytes()).hexdigest(), encoding="ascii"
            )
            for module in MODULES:
                with self.subTest(module=module.__name__):
                    frame = module.verified_frame(
                        "plan", plan,
                        attestation=root / ".attestation",
                        mode=root / ".mode",
                    )
                    self.assertIn("# Approved", frame)

    def test_unsafe_or_oversized_mode_marker_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = root / "task_plan.md"
            plan.write_text("# Plan\n", encoding="utf-8")
            mode = root / ".mode"
            for marker in (b"autonomous surprise\n", b"autonomous\xff\n", b"autonomous " * 40):
                mode.write_bytes(marker)
                for module in MODULES:
                    with self.subTest(module=module.__name__, size=len(marker)):
                        with self.assertRaises((ValueError, UnicodeError)):
                            module.verified_frame("plan", plan, mode=mode)

    def test_attestation_is_bounded_no_follow_and_never_disclosed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = root / "task_plan.md"
            plan.write_text("# Current\n", encoding="utf-8")
            attestation = root / ".attestation"
            secret_expected = "a" * 64
            attestation.write_text(secret_expected, encoding="ascii")
            for module in MODULES:
                with self.subTest(module=module.__name__, case="mismatch"):
                    with self.assertRaises(ValueError) as caught:
                        module.verified_frame("plan", plan, attestation=attestation)
                    self.assertNotIn(secret_expected, str(caught.exception))
            attestation.write_bytes(b"a" * 129)
            for module in MODULES:
                with self.subTest(module=module.__name__, case="oversized"):
                    with self.assertRaises(ValueError):
                        module.verified_frame("plan", plan, attestation=attestation)

    def test_plan_progress_attestation_and_mode_symlinks_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside_tmp:
            root = Path(tmp)
            outside = Path(outside_tmp)
            outside_file = outside / "outside"
            outside_file.write_text("outside\n", encoding="utf-8")
            probe = root / "probe"
            try:
                probe.symlink_to(outside_file)
            except OSError:
                self.skipTest("file symlink creation is unavailable on this host")
            for module in MODULES:
                for name in ("task_plan.md", "progress.md", ".attestation", ".mode"):
                    link = root / name
                    link.symlink_to(outside_file)
                    with self.subTest(module=module.__name__, name=name):
                        if name in ("task_plan.md", "progress.md"):
                            with self.assertRaises(ValueError):
                                module.read_regular_bytes(link)
                        elif name == ".attestation":
                            plan = root / "safe-plan"
                            plan.write_text("safe\n", encoding="utf-8")
                            with self.assertRaises(ValueError):
                                module.verified_frame("plan", plan, attestation=link)
                        else:
                            plan = root / "safe-plan"
                            plan.write_text("safe\n", encoding="utf-8")
                            with self.assertRaises(ValueError):
                                module.verified_frame("plan", plan, mode=link)
                    link.unlink()

    @unittest.skipUnless(os.name == "nt", "Windows junction regression")
    def test_windows_junction_component_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside_tmp:
            root = Path(tmp)
            outside = Path(outside_tmp)
            (outside / "task_plan.md").write_text("outside\n", encoding="utf-8")
            junction = root / "junction"
            create = subprocess.run(
                ["cmd", "/d", "/c", "mklink", "/J", str(junction), str(outside)],
                text=True,
                encoding="utf-8",
                capture_output=True,
                check=False,
            )
            if create.returncode != 0:
                self.skipTest(f"junction creation unavailable: {create.stderr.strip()}")
            try:
                for module in MODULES:
                    with self.subTest(module=module.__name__):
                        with self.assertRaises(ValueError):
                            module.read_regular_bytes(junction / "task_plan.md")
            finally:
                os.rmdir(junction)

    @unittest.skipUnless(os.name == "nt", "Windows junction swap regression")
    def test_windows_component_swap_to_external_junction_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside_tmp:
            root = Path(tmp)
            container = root / "container"
            container.mkdir()
            source = container / "task_plan.md"
            source.write_text("approved\n", encoding="utf-8")
            outside = Path(outside_tmp)
            (outside / "task_plan.md").write_text("hostile\n", encoding="utf-8")
            for index, module in enumerate(MODULES):
                if container.exists() and not container.is_symlink():
                    for child in container.iterdir():
                        child.unlink()
                    container.rmdir()
                container.mkdir()
                source.write_text("approved\n", encoding="utf-8")
                backup = root / f"original-{index}"
                original_check = module._assert_no_reparse_components
                swapped = False

                def swap_after_check(path):
                    nonlocal swapped
                    result = original_check(path)
                    if not swapped:
                        container.rename(backup)
                        create = subprocess.run(
                            ["cmd", "/d", "/c", "mklink", "/J", str(container), str(outside)],
                            text=True,
                            encoding="utf-8",
                            capture_output=True,
                            check=False,
                        )
                        if create.returncode != 0:
                            backup.rename(container)
                            raise unittest.SkipTest("junction creation unavailable")
                        swapped = True
                    return result

                module._assert_no_reparse_components = swap_after_check
                try:
                    with self.subTest(module=module.__name__):
                        with self.assertRaises(ValueError):
                            module.read_regular_bytes(source)
                finally:
                    module._assert_no_reparse_components = original_check
                    if swapped:
                        os.rmdir(container)
                        backup.rename(container)

    def test_swap_to_external_symlink_is_rejected_when_supported(self) -> None:
        if os.name == "nt":
            self.skipTest("deterministic file symlink swap unavailable on this Windows host")
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside_tmp:
            source = Path(tmp) / "task_plan.md"
            source.write_text("approved\n", encoding="utf-8")
            outside = Path(outside_tmp) / "outside"
            outside.write_text("hostile\n", encoding="utf-8")
            for module in MODULES:
                source.write_text("approved\n", encoding="utf-8")
                original = module._assert_no_reparse_components
                swapped = False

                def swap_after_validation(path):
                    nonlocal swapped
                    result = original(path)
                    if not swapped:
                        source.unlink()
                        source.symlink_to(outside)
                        swapped = True
                    return result

                module._assert_no_reparse_components = swap_after_validation
                try:
                    with self.subTest(module=module.__name__):
                        with self.assertRaises((OSError, ValueError)):
                            module.read_regular_bytes(source)
                finally:
                    module._assert_no_reparse_components = original
                    if source.is_symlink():
                        source.unlink()


if __name__ == "__main__":
    unittest.main()
