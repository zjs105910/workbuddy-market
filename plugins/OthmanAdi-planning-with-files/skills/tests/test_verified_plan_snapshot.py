"""Security regressions for exact-byte plan attestation and emission."""
from __future__ import annotations

import hashlib
import os
import shutil
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INJECT = REPO_ROOT / "skills" / "planning-with-files" / "scripts" / "inject-plan.sh"


@unittest.skipUnless(shutil.which("sh"), "POSIX shell is unavailable")
class VerifiedPlanSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="pwf-verified-snapshot-")
        self.root = Path(self.temp.name)
        self.cache = self.root / "cache"
        self.cache.mkdir()
        self.plan = self.root / "task_plan.md"
        self.plan.write_text("# Approved plan\nAPPROVED_BYTES\n", encoding="utf-8")
        digest = hashlib.sha256(self.plan.read_bytes()).hexdigest()
        (self.root / ".plan-attestation").write_text(digest, encoding="ascii")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _run(self, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        child_env = os.environ.copy()
        for name in (
            "PLAN_ID",
            "PWF_PLAN_ROOT",
            "PWF_SESSION_ID",
            "PLANNING_DISABLED",
            "PWF_TRUSTED_PYTHON",
            "PYTHON_BIN",
        ):
            child_env.pop(name, None)
        child_env["XDG_CACHE_HOME"] = str(self.cache)
        if env:
            child_env.update(env)
        command = ["sh", str(INJECT), "--context=userprompt"]
        if env and env.get("PWF_TEST_PATH"):
            command = [
                "sh", "-c", 'PATH="$1"; shift; export PATH; exec sh "$@"',
                "sh", env["PWF_TEST_PATH"], str(INJECT), "--context=userprompt",
            ]
        return subprocess.run(
            command,
            cwd=self.root,
            env=child_env,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
            timeout=30,
        )

    def test_restored_whole_second_mtime_cannot_reuse_an_old_digest(self) -> None:
        first = self._run()
        self.assertIn("APPROVED_BYTES", first.stdout)
        original = self.plan.stat()
        self.plan.write_text("# Hostile replacement\nRESTORED_MTIME_ATTACK\n", encoding="utf-8")
        os.utime(self.plan, ns=(original.st_atime_ns, original.st_mtime_ns))

        second = self._run()
        self.assertIn("PLAN TAMPERED", second.stdout)
        self.assertNotIn("RESTORED_MTIME_ATTACK", second.stdout)
        self.assertFalse((self.cache / "pwf-sha").exists())

    def test_swap_after_snapshot_does_not_change_emitted_verified_bytes(self) -> None:
        wrappers = self.root / "bin"
        wrappers.mkdir()
        real_sha = shutil.which("sha256sum")
        if not real_sha:
            self.skipTest("sha256sum is unavailable")
        wrapper = wrappers / "sha256sum"
        wrapper.write_text(
            "#!/bin/sh\n"
            "if [ -n \"${PWF_SWAP_TARGET:-}\" ]; then\n"
            "  printf '%s\\n' '# swapped' 'SWAP_AFTER_CHECK_ATTACK' > \"$PWF_SWAP_TARGET\"\n"
            "  unset PWF_SWAP_TARGET\n"
            "fi\n"
            'exec /usr/bin/sha256sum "$@"\n',
            encoding="utf-8",
            newline="\n",
        )
        wrapper.chmod(0o755)
        if os.name == "nt":
            converted = subprocess.run(
                ["sh", "-lc", 'printf "%s\n%s\n" "$(cygpath -u "$1")" "$(cygpath -u "$2")"', "sh", str(wrappers), str(self.plan)],
                text=True,
                encoding="utf-8",
                capture_output=True,
                check=True,
            ).stdout.splitlines()
            shell_wrappers, shell_plan = converted
        else:
            shell_wrappers, shell_plan = str(wrappers), str(self.plan)
        result = self._run(env={
            "PWF_TEST_PATH": shell_wrappers + ":/usr/bin:/bin",
            "PWF_SWAP_TARGET": shell_plan,
            "PWF_TRUSTED_PYTHON": str(Path(sys.executable).resolve()),
        })
        self.assertIn("APPROVED_BYTES", result.stdout)
        self.assertNotIn("SWAP_AFTER_CHECK_ATTACK", result.stdout)
        self.assertIn("SWAP_AFTER_CHECK_ATTACK", self.plan.read_text(encoding="utf-8"))
        snapshots = self.cache / "pwf-snapshots"
        self.assertEqual([], list(snapshots.iterdir()))

    def test_unsupported_relative_pin_fails_closed(self) -> None:
        result = self._run(env={"PWF_PLAN_ROOT": "."})
        self.assertNotIn("APPROVED_BYTES", result.stdout)
        self.assertIn("not a supported absolute local directory", result.stdout)

    def test_plan_frame_reports_truthful_byte_truncation(self) -> None:
        self.plan.write_bytes(b"X" * 70_000)
        digest = hashlib.sha256(self.plan.read_bytes()).hexdigest()
        (self.root / ".plan-attestation").write_text(digest, encoding="ascii")
        result = self._run()
        match = re.search(
            r"kind=plan nonce=[0-9a-f]{24} bytes=(\d+) .*truncated=true",
            result.stdout,
        )
        self.assertIsNotNone(match, result.stdout)
        assert match is not None
        self.assertEqual(64 * 1024, int(match.group(1)))

    def test_symlink_plan_is_refused_when_supported(self) -> None:
        outside = self.root / "outside-plan.md"
        outside.write_text("OUTSIDE_SYMLINK_PLAN\n", encoding="utf-8")
        self.plan.unlink()
        try:
            self.plan.symlink_to(outside)
        except OSError:
            self.skipTest("file symlink creation is unavailable on this host")
        result = self._run()
        self.assertNotIn("OUTSIDE_SYMLINK_PLAN", result.stdout)


if __name__ == "__main__":
    unittest.main()
